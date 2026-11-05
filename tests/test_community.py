from datetime import datetime, timedelta
import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
from pathlib import Path
from curri.catalog import Catalog
from curri.community import KST, Community
from curri.meeting_links import GoogleMeet, MeetingLinkError, Zoom, load_provider
from curri.server import make_server
from curri.store import Store
from test_catalog import fixture

CONCEPTS = {'_about': 'test', 'concepts': [{'id': 'machine_learning', 'ko': 'AI·기계학습', 'kind': 'method', 'keywords': []}, {'id': 'robotics', 'ko': '로봇', 'kind': 'domain', 'keywords': []}]}
SEED = {'demo_password': 'demo-password-1', 'users': [
    {'key': 'g1', 'email': 'grad@postech.example', 'nickname': '김선배', 'role': 'graduate', 'lab_id': 'duplicate',
     'account': {'real_name': '김선배', 'school': 'POSTECH', 'program': '박사과정', 'research': '생명 AI', 'interest_tags': ['machine_learning'], 'contact_consent': True}},
    {'key': 'g2', 'email': 'hidden@postech.example', 'nickname': '숨은선배', 'role': 'graduate', 'lab_id': 'bio',
     'account': {'real_name': '숨은선배', 'school': 'POSTECH', 'interest_tags': ['machine_learning'], 'contact_consent': False}},
    {'key': 'g3', 'email': 'gone@postech.example', 'nickname': '없는랩', 'role': 'graduate', 'lab_id': 'no_such_lab', 'account': {}},
    {'key': 's1', 'email': 'stu@postech.example', 'nickname': '후기러', 'role': 'student',
     'account': {'real_name': '이학생', 'school': 'POSTECH', 'department': '컴퓨터공학과', 'interest_tags': ['robotics']}}],
    'reviews': [{'author': 's1', 'lab_id': 'bio', 'term': '2025 여름방학', 'duration': '8주', 'activity': '논문 읽기와 재현 실험', 'ratings': {'mentoring': 5, 'learning': 4, 'workload': 4, 'atmosphere': 5},
                 'good': '피드백이 빨랐어요.', 'improve': '', 'recommend_for': '', 'created': 1750000000}],
    'threads': [{'student': 's1', 'graduate': 'g1', 'subject': '질문', 'messages': [{'from': 's1', 'body': '안녕하세요 질문 있어요', 'created': 1758000000}, {'from': 'g1', 'body': '네 반가워요', 'created': 1758001000}]}]}
ACCOUNT = {'real_name': '홍길동', 'nickname': '길동', 'school': 'POSTECH', 'interest_tags': ['robotics'], 'interest_text': '', 'grade': '3학년', 'intro': '<b>안녕</b>'}
REVIEW = {'lab_id': 'bio', 'completed': True, 'term': '2026 여름방학', 'duration': '한 학기', 'activity': '데이터 정리와 실험 자동화를 맡았어요',
          'good': '선배들이 친절하게 알려줬어요', 'improve': '', 'recommend_for': '', 'ratings': {'mentoring': 4, 'learning': 5, 'workload': 3, 'atmosphere': 4}}


def setup_data(root):
    fixture(root)
    (root / 'concepts.json').write_text(json.dumps(CONCEPTS))
    (root / 'community_seed.json').write_text(json.dumps(SEED, ensure_ascii=False))


class CommunityUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        setup_data(self.root)
        self.store = Store(self.root / 'db.sqlite')
        self.community = Community(self.store, Catalog(self.root), self.root)

    def test_account_validation_requires_core_fields_and_known_tags(self):
        nickname, account = self.community.clean_account(ACCOUNT)
        self.assertEqual((nickname, account['grade'], account['interest_tags']), ('길동', '3학년', ['robotics']))
        for broken in ({**ACCOUNT, 'real_name': ''}, {**ACCOUNT, 'nickname': 'a b'}, {**ACCOUNT, 'school': ' '},
                       {**ACCOUNT, 'interest_tags': [], 'interest_text': ''}, {**ACCOUNT, 'interest_tags': ['made_up']},
                       {**ACCOUNT, 'grade': '10학년'}, {**ACCOUNT, 'intro': 'x' * 1501}, None):
            with self.assertRaises(ValueError):
                self.community.clean_account(broken)
        self.assertEqual(self.community.clean_account({**ACCOUNT, 'interest_tags': [], 'interest_text': '로봇 팔'})[1]['interest_text'], '로봇 팔')

    def test_seed_is_idempotent_resolves_aliases_and_skips_unknown_labs(self):
        Community(self.store, Catalog(self.root), self.root)
        with self.store.db() as db:
            counts = [db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('users', 'reviews', 'threads', 'messages')]
            grad_lab = db.execute("SELECT lab_id FROM users WHERE email='grad@postech.example'").fetchone()[0]
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users WHERE dummy=1').fetchone()[0], 3)
        self.assertEqual(counts, [3, 1, 1, 2])
        self.assertEqual(grad_lab, 'bio')  # 'duplicate' shares the bio homepage

    def test_existing_database_is_migrated(self):
        path = self.root / 'old.sqlite'
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, profile TEXT NOT NULL DEFAULT '{}')")
            db.execute("INSERT INTO users(email,salt,password_hash) VALUES ('old@example.com','00','x')")
        store = Store(path)
        with store.db() as db:
            row = db.execute('SELECT role, account, nickname FROM users').fetchone()
        self.assertEqual(tuple(row), ('student', '{}', None))


class CommunityHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        setup_data(root)
        catalog, store = Catalog(root), Store(root / 'app.sqlite')
        self.server = make_server('127.0.0.1', 0, catalog, store, community=Community(store, catalog, root))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def client(self):
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def request(path, data=None):
            req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={'Content-Type': 'application/json', 'Origin': self.url})
            try:
                response = opener.open(req)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())
        request('/api/session')
        return request

    def test_guest_sees_reviews_and_graduates_without_email(self):
        guest = self.client()
        status, data = guest('/api/community?lab_id=duplicate')
        self.assertEqual(status, 200)
        self.assertEqual(data['lab_id'], 'bio')
        self.assertEqual(data['summary']['count'], 1)
        self.assertEqual(data['reviews'][0]['author'], {'nickname': '후기러', 'department': '컴퓨터공학과', 'grade': ''})
        self.assertNotIn('이학생', json.dumps(data, ensure_ascii=False))  # real names never appear on reviews
        self.assertEqual([(g['name'], g['email']) for g in data['graduates']], [('김선배', None)])  # no consent → hidden
        self.assertEqual(guest('/api/community?lab_id=nope')[0], 404)
        self.assertEqual(guest('/api/review', REVIEW)[1]['code'], 'login_required')
        self.assertEqual(guest('/api/inbox')[0], 401)
        self.assertEqual(len(guest('/api/reviews')[1]['reviews']), 1)
        self.assertEqual(len(guest('/api/concepts')[1]['concepts']), 2)

    def test_review_contact_reply_and_privacy(self):
        student = self.client()
        self.assertEqual(student('/api/register', {'email': 'new@example.com', 'password': 'valid-password', 'account': {**ACCOUNT, 'nickname': '후기러'}})[0], 400)  # nickname taken
        self.assertEqual(student('/api/register', {'email': 'new@example.com', 'password': 'valid-password', 'account': ACCOUNT})[0], 200)
        community = student('/api/community?lab_id=bio')[1]
        grad = community['graduates'][0]
        self.assertEqual(grad['email'], 'grad@postech.example')
        self.assertEqual(student('/api/review', {**REVIEW, 'completed': False})[0], 400)
        self.assertEqual(student('/api/review', {**REVIEW, 'ratings': {**REVIEW['ratings'], 'mentoring': 6}})[0], 400)
        status, saved = student('/api/review', REVIEW)
        self.assertEqual((status, saved['summary']['count'], saved['my_review']['term']), (200, 2, '2026 여름방학'))
        status, saved = student('/api/review', {**REVIEW, 'term': '2026 가을학기'})
        self.assertEqual((saved['summary']['count'], saved['my_review']['term']), (2, '2026 가을학기'))  # one review per lab, updated
        self.assertEqual(student('/api/contact', {'graduate_id': grad['id'], 'subject': '질문', 'body': '짧음'})[0], 400)
        status, sent = student('/api/contact', {'graduate_id': grad['id'], 'subject': '연구참여 질문', 'body': '안녕하세요, 연구참여 준비를 여쭤보고 싶어요.'})
        self.assertEqual(status, 200)
        self.assertEqual(student('/api/contact', {'graduate_id': 999, 'subject': '연구참여 질문', 'body': '안녕하세요, 질문이 있어요.'})[0], 404)

        graduate = self.client()
        self.assertEqual(graduate('/api/login', {'email': 'grad@postech.example', 'password': 'demo-password-1'})[0], 200)
        self.assertEqual(graduate('/api/session')[1]['unread'], 1)  # the seeded question was already answered
        inbox = graduate('/api/inbox')[1]
        mine = next(t for t in inbox['threads'] if t['id'] == sent['thread_id'])
        self.assertEqual(mine['other']['nickname'], '길동')
        status, thread = graduate(f"/api/thread?id={sent['thread_id']}")
        self.assertEqual(thread['other']['email'], 'new@example.com')
        self.assertEqual(thread['other']['intro'], '<b>안녕</b>')
        self.assertEqual(graduate('/api/review', REVIEW)[0], 400)  # graduates do not review
        self.assertEqual(graduate('/api/reply', {'thread_id': sent['thread_id'], 'body': '반가워요! 편하게 물어보세요.'})[0], 200)

        self.assertEqual(student('/api/session')[1]['unread'], 1)
        status, thread = student(f"/api/thread?id={sent['thread_id']}")
        self.assertEqual([m['mine'] for m in thread['messages']], [True, False])
        self.assertEqual(student('/api/session')[1]['unread'], 0)

        stranger = self.client()
        stranger('/api/register', {'email': 'x@example.com', 'password': 'valid-password', 'account': {**ACCOUNT, 'nickname': '구경꾼'}})
        self.assertEqual(stranger(f"/api/thread?id={sent['thread_id']}")[0], 404)
        self.assertEqual(stranger('/api/reply', {'thread_id': sent['thread_id'], 'body': '끼어들기'})[0], 404)
        self.assertEqual(student('/api/review/delete', {'lab_id': 'bio'})[1]['summary']['count'], 1)

    def test_incomplete_profile_cannot_review_or_contact_until_completed(self):
        user = self.client()
        token_store = Store(Path(self.tmp.name) / 'app.sqlite')
        # An account created before profiles existed has no nickname or account fields.
        session = token_store.session(None)
        token_store.authenticate(session, 'legacy@example.com', 'valid-password', register=True)
        user('/api/login', {'email': 'legacy@example.com', 'password': 'valid-password'})
        self.assertFalse(user('/api/session')[1]['user']['profile_complete'])
        status, error = user('/api/review', REVIEW)
        self.assertEqual((status, error['code']), (403, 'profile_required'))
        status, snapshot = user('/api/account', ACCOUNT)
        self.assertEqual(status, 200)
        self.assertTrue(snapshot['user']['profile_complete'])
        self.assertEqual(user('/api/review', REVIEW)[0], 200)



class FakeLinks:
    name, label = 'google', 'Google Meet'

    def __init__(self):
        self.created, self.cancelled, self.fail = [], [], False

    def create(self, topic, description, start, minutes, attendees):
        if self.fail:
            raise MeetingLinkError('화상회의 링크를 만들지 못했어요.')
        self.created.append((topic, start, minutes, attendees))
        return {'join_url': f'https://meet.google.com/abc-{len(self.created)}', 'external_id': f'evt{len(self.created)}'}

    def cancel(self, external_id):
        self.cancelled.append(external_id)


def slot(days, hour=14):
    d = (datetime.now(KST) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return d.strftime('%Y-%m-%dT%H:%M'), int(d.timestamp())


class MeetingHttpTests(unittest.TestCase):
    client = CommunityHttpTests.client

    def setUp(self):
        self.links = FakeLinks()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        setup_data(root)
        catalog, store = Catalog(root), Store(root / 'app.sqlite')
        self.community = Community(store, catalog, root, meeting_links=self.links)
        self.server = make_server('127.0.0.1', 0, catalog, store, community=self.community)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.student, self.graduate = self.client(), self.client()
        self.student('/api/register', {'email': 'new@example.com', 'password': 'valid-password', 'account': ACCOUNT})
        grad = self.student('/api/community?lab_id=bio')[1]['graduates'][0]
        self.thread_id = self.student('/api/contact', {'graduate_id': grad['id'], 'subject': '연구참여 질문', 'body': '안녕하세요, 연구참여 준비를 여쭤보고 싶어요.'})[1]['thread_id']
        self.graduate('/api/login', {'email': 'grad@postech.example', 'password': 'demo-password-1'})

    def test_online_meeting_confirmation_books_a_link_and_notifies(self):
        (a, a_ts), (b, b_ts) = slot(2), slot(3, 10)
        request = {'thread_id': self.thread_id, 'mode': 'online', 'minutes': 20, 'slots': [b, a], 'note': '연구실 분위기가 궁금해요'}
        for broken in ({**request, 'mode': 'phone'}, {**request, 'minutes': 25}, {**request, 'minutes': 60}, {**request, 'slots': []}, {**request, 'slots': [a, a]},
                       {**request, 'slots': [slot(0, 0)[0]]}, {**request, 'slots': [slot(90)[0]]}, {**request, 'slots': ['내일 오후']},
                       {**request, 'mode': 'offline'}):
            self.assertEqual(self.student('/api/meeting/request', broken)[0], 400, broken)
        status, thread = self.student('/api/meeting/request', request)
        self.assertEqual(status, 200)
        meeting = thread['meetings'][0]
        self.assertEqual((meeting['status'], meeting['slots'], meeting['can_confirm'], thread['meeting_link']['label']), ('requested', [a_ts, b_ts], False, 'Google Meet'))
        self.assertIn('📅 만남 요청 · 온라인 20분', thread['messages'][-1]['body'])
        self.assertEqual(self.student('/api/meeting/request', request)[0], 400)  # one open request per conversation
        self.assertEqual(self.student('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})[0], 400)  # proposer cannot confirm

        stranger = self.client()
        stranger('/api/register', {'email': 'x@example.com', 'password': 'valid-password', 'account': {**ACCOUNT, 'nickname': '구경꾼'}})
        self.assertEqual(stranger('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})[0], 404)
        self.assertEqual(stranger('/api/meeting/cancel', {'meeting_id': meeting['id']})[0], 404)

        self.assertEqual(self.graduate('/api/session')[1]['unread'], 2)  # first message + meeting request
        self.assertEqual(self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts + 60})[0], 400)
        self.links.fail = True
        status, error = self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})
        self.assertEqual((status, error['code']), (502, 'meeting_link_failed'))
        self.links.fail = False
        status, thread = self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})
        self.assertEqual(status, 200)
        confirmed = thread['meetings'][0]
        self.assertEqual((confirmed['status'], confirmed['start'], confirmed['provider'], confirmed['join_url']), ('confirmed', a_ts, 'google', 'https://meet.google.com/abc-1'))
        topic, start, minutes, attendees = self.links.created[0]
        self.assertEqual((int(start.timestamp()), minutes, attendees), (a_ts, 20, ['new@example.com', 'grad@postech.example']))
        self.assertIn('홍길동 · 김선배', topic)
        self.assertIn('접속 링크: https://meet.google.com/abc-1', thread['messages'][-1]['body'])
        self.assertEqual(self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})[0], 400)  # already confirmed

        student_view = self.student(f'/api/thread?id={self.thread_id}')[1]
        self.assertEqual(student_view['meetings'][0]['join_url'], 'https://meet.google.com/abc-1')
        self.assertEqual(self.student('/api/meeting/cancel', {'meeting_id': meeting['id']})[0], 200)
        self.assertEqual(self.links.cancelled, ['evt1'])
        self.assertEqual(self.student('/api/meeting/cancel', {'meeting_id': meeting['id']})[0], 400)
        self.assertEqual(self.student('/api/meeting/request', request)[0], 200)  # a new request after cancelling

    def test_manual_link_and_offline_meetings(self):
        (a, a_ts) = slot(4)
        meeting = self.graduate('/api/meeting/request', {'thread_id': self.thread_id, 'mode': 'online', 'minutes': 30, 'slots': [a]})[1]['meetings'][0]
        self.assertEqual(self.student('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts, 'join_url': 'javascript:alert(1)'})[0], 400)
        confirmed = self.student('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts, 'join_url': 'https://zoom.us/j/123'})[1]['meetings'][0]
        self.assertEqual((confirmed['provider'], confirmed['join_url']), ('manual', 'https://zoom.us/j/123'))
        self.assertEqual(self.links.created, [])
        self.graduate('/api/meeting/cancel', {'meeting_id': meeting['id']})
        self.assertEqual(self.links.cancelled, [])  # nothing was booked on the provider

        offline = self.student('/api/meeting/request', {'thread_id': self.thread_id, 'mode': 'offline', 'slots': [a], 'place': '학생회관 카페'})[1]['meetings'][0]
        declined = self.graduate('/api/meeting/cancel', {'meeting_id': offline['id']})[1]
        self.assertEqual(declined['meetings'][0]['status'], 'cancelled')
        self.assertIn('다른 시간으로 다시 요청', declined['messages'][-1]['body'])
        offline = self.student('/api/meeting/request', {'thread_id': self.thread_id, 'mode': 'offline', 'slots': [a], 'place': '학생회관 카페'})[1]['meetings'][0]
        confirmed = self.graduate('/api/meeting/confirm', {'meeting_id': offline['id'], 'start': a_ts})[1]['meetings'][0]
        self.assertEqual((confirmed['status'], confirmed['join_url'], confirmed['place']), ('confirmed', None, '학생회관 카페'))

    def test_without_a_provider_online_confirmation_needs_a_link(self):
        self.community.meeting_links = None
        (a, a_ts) = slot(1)
        meeting = self.student('/api/meeting/request', {'thread_id': self.thread_id, 'mode': 'online', 'slots': [a]})[1]['meetings'][0]
        status, thread = self.graduate(f'/api/thread?id={self.thread_id}')
        self.assertIsNone(thread['meeting_link'])
        self.assertEqual(self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts})[0], 400)
        self.assertEqual(self.graduate('/api/meeting/confirm', {'meeting_id': meeting['id'], 'start': a_ts, 'join_url': 'https://meet.google.com/x'})[0], 200)


class MeetingProviderConfigTests(unittest.TestCase):
    def test_config_file_selects_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'links.json'
            self.assertIsNone(load_provider(path))
            path.write_text(json.dumps({'provider': 'zoom', 'account_id': 'a', 'client_id': 'b', 'client_secret': 'c'}))
            self.assertEqual(load_provider(path).label, 'Zoom')
            path.write_text(json.dumps({'provider': 'google', 'client_id': 'b'}))
            with self.assertRaises(ValueError):
                load_provider(path)
            path.write_text(json.dumps({'provider': 'teams'}))
            with self.assertRaises(ValueError):
                load_provider(path)


    def test_providers_send_expected_requests(self):
        calls = []

        def fake(method, url, headers=None, body=None, form=None):
            calls.append((method, url, headers, body, form))
            if 'token' in url:
                return {'access_token': 'tok', 'expires_in': 3600}
            if 'calendar' in url and method == 'POST':
                return {'id': 'evt', 'hangoutLink': 'https://meet.google.com/xyz'}
            if 'zoom' in url and method == 'POST':
                return {'id': 85012345, 'join_url': 'https://us06web.zoom.us/j/85012345'}
            return {}
        start = datetime(2026, 11, 7, 14, 0, tzinfo=KST)
        with mock.patch('curri.meeting_links._call', fake):
            google = GoogleMeet({'client_id': 'id', 'client_secret': 'sec', 'refresh_token': 'ref'})
            self.assertEqual(google.create('t', 'd', start, 20, ['a@x.com', 'b@x.com']), {'join_url': 'https://meet.google.com/xyz', 'external_id': 'evt'})
            google.cancel('evt')
            zoom = Zoom({'account_id': 'acc', 'client_id': 'id', 'client_secret': 'sec'})
            self.assertEqual(zoom.create('t', 'd', start, 30, []), {'join_url': 'https://us06web.zoom.us/j/85012345', 'external_id': '85012345'})
        token, event, delete, ztoken, zmeeting = calls
        self.assertEqual(token[4]['grant_type'], 'refresh_token')
        self.assertIn('/calendars/primary/events?conferenceDataVersion=1&sendUpdates=none', event[1])
        self.assertEqual((event[3]['start']['dateTime'], event[3]['end']['dateTime']), ('2026-11-07T14:00:00+09:00', '2026-11-07T14:20:00+09:00'))
        self.assertEqual(event[3]['conferenceData']['createRequest']['conferenceSolutionKey'], {'type': 'hangoutsMeet'})
        self.assertEqual([a['email'] for a in event[3]['attendees']], ['a@x.com', 'b@x.com'])
        self.assertEqual((delete[0], delete[2]['Authorization']), ('DELETE', 'Bearer tok'))  # token reused
        self.assertIn('grant_type=account_credentials&account_id=acc', ztoken[1])
        self.assertEqual((zmeeting[3]['start_time'], zmeeting[3]['timezone'], zmeeting[3]['duration'], zmeeting[3]['settings']['join_before_host']),
                         ('2026-11-07T14:00:00', 'Asia/Seoul', 30, True))


if __name__ == '__main__':
    unittest.main()
