"""Online meeting links for confirmed student–graduate meetings.

The service books the meeting on its own Google Calendar (with a Meet link) or Zoom account. Credentials
live in a local JSON file (default `.local/meeting_links.json`); without it the confirming person pastes
a link by hand. Provider errors never expose credentials or response bodies to the user.
"""
import base64
from datetime import timedelta
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

TIMEOUT = 10


class MeetingLinkError(Exception):
    pass


def _call(method, url, headers=None, body=None, form=None):
    data = None
    headers = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        print(f'meeting link provider error: HTTP {exc.code} {method} {urllib.parse.urlsplit(url).netloc}', flush=True)
        raise MeetingLinkError('화상회의 링크를 만들지 못했어요. 잠시 후 다시 시도하거나 링크를 직접 입력해 주세요.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        print(f'meeting link provider unreachable: {method} {urllib.parse.urlsplit(url).netloc}', flush=True)
        raise MeetingLinkError('화상회의 서비스에 연결하지 못했어요. 잠시 후 다시 시도하거나 링크를 직접 입력해 주세요.') from None
    return json.loads(raw) if raw else {}


class _TokenCache:
    def __init__(self):
        self.lock = threading.Lock()
        self.token, self.expires = None, 0.0

    def get(self, fetch):
        with self.lock:
            if not self.token or time.time() > self.expires - 60:
                result = fetch()
                self.token, self.expires = result['access_token'], time.time() + float(result.get('expires_in', 3600))
            return self.token


class GoogleMeet:
    """Google Calendar event with a Meet conference, on the calendar of the account that granted the refresh token."""
    name = 'google'
    label = 'Google Meet'

    def __init__(self, config):
        self.client_id, self.client_secret, self.refresh_token = config['client_id'], config['client_secret'], config['refresh_token']
        self.calendar = urllib.parse.quote(config.get('calendar_id', 'primary'), safe='')
        self.send_invites = bool(config.get('send_invites', False))
        self.tokens = _TokenCache()

    def _token(self):
        return self.tokens.get(lambda: _call('POST', 'https://oauth2.googleapis.com/token', form={
            'client_id': self.client_id, 'client_secret': self.client_secret, 'refresh_token': self.refresh_token, 'grant_type': 'refresh_token'}))

    def _updates(self):
        return 'all' if self.send_invites else 'none'

    def create(self, topic, description, start, minutes, attendees):
        # Invited Google accounts can enter without the organizer admitting them.
        event = {'summary': topic, 'description': description,
                 'start': {'dateTime': start.isoformat(), 'timeZone': 'Asia/Seoul'},
                 'end': {'dateTime': (start + timedelta(minutes=minutes)).isoformat(), 'timeZone': 'Asia/Seoul'},
                 'attendees': [{'email': e} for e in attendees if e], 'guestsCanSeeOtherGuests': True,
                 'conferenceData': {'createRequest': {'requestId': uuid.uuid4().hex, 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}}
        url = f'https://www.googleapis.com/calendar/v3/calendars/{self.calendar}/events?conferenceDataVersion=1&sendUpdates={self._updates()}'
        result = _call('POST', url, {'Authorization': f'Bearer {self._token()}'}, event)
        link = result.get('hangoutLink') or next((p.get('uri') for p in result.get('conferenceData', {}).get('entryPoints', []) if p.get('entryPointType') == 'video'), None)
        if not link:
            if result.get('id'):
                self.cancel(result['id'])
            raise MeetingLinkError('Google Meet 링크가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.')
        return {'join_url': link, 'external_id': result['id']}

    def cancel(self, external_id):
        url = f'https://www.googleapis.com/calendar/v3/calendars/{self.calendar}/events/{urllib.parse.quote(external_id, safe="")}?sendUpdates={self._updates()}'
        _call('DELETE', url, {'Authorization': f'Bearer {self._token()}'})


class Zoom:
    """Scheduled meeting on a Zoom Server-to-Server OAuth app's account. Guests may join before the host."""
    name = 'zoom'
    label = 'Zoom'

    def __init__(self, config):
        self.account_id, self.client_id, self.client_secret = config['account_id'], config['client_id'], config['client_secret']
        self.user = urllib.parse.quote(config.get('user_id', 'me'), safe='@')
        self.tokens = _TokenCache()

    def _token(self):
        basic = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()
        url = 'https://zoom.us/oauth/token?' + urllib.parse.urlencode({'grant_type': 'account_credentials', 'account_id': self.account_id})
        return self.tokens.get(lambda: _call('POST', url, {'Authorization': f'Basic {basic}'}))

    def create(self, topic, description, start, minutes, attendees):
        body = {'topic': topic[:200], 'type': 2, 'start_time': start.strftime('%Y-%m-%dT%H:%M:%S'), 'timezone': 'Asia/Seoul', 'duration': minutes,
                'agenda': description[:2000], 'settings': {'join_before_host': True, 'jbh_time': 0, 'waiting_room': False}}
        result = _call('POST', f'https://api.zoom.us/v2/users/{self.user}/meetings', {'Authorization': f'Bearer {self._token()}'}, body)
        if not result.get('join_url'):
            raise MeetingLinkError('Zoom 링크를 만들지 못했어요. 잠시 후 다시 시도해 주세요.')
        return {'join_url': result['join_url'], 'external_id': str(result['id'])}

    def cancel(self, external_id):
        _call('DELETE', f'https://api.zoom.us/v2/meetings/{urllib.parse.quote(external_id, safe="")}', {'Authorization': f'Bearer {self._token()}'})


PROVIDERS = {'google': GoogleMeet, 'zoom': Zoom}


def load_provider(path):
    """Provider from the config file, or None when the file is absent."""
    if not path or not Path(path).is_file():
        return None
    config = json.loads(Path(path).read_text())
    kind = config.get('provider')
    if kind not in PROVIDERS:
        raise ValueError(f'화상회의 설정의 provider는 {", ".join(PROVIDERS)} 중 하나여야 합니다.')
    try:
        return PROVIDERS[kind](config)
    except KeyError as exc:
        raise ValueError(f'화상회의 설정에 {exc.args[0]} 값이 없습니다.') from None
