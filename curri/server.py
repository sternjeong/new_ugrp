"""Local JSON API; all exploration authorization is enforced server-side."""
from collections import defaultdict, deque
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit, parse_qs
from .community import Community, NotFound
from .meeting_links import MeetingLinkError
from .store import LoginRequired, InvalidCredentials, ProfileRequired

STATIC = Path(__file__).parent / 'static'


def make_server(host, port, catalog, store, secure_cookie=False, community=None, engine=None, broker=None):
    attempts = defaultdict(deque)
    searches = defaultdict(deque)
    community = community or Community(store, catalog)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'Curri/0.1'

        def log_message(self, format, *args):
            pass

        def client_ip(self):
            # 서버는 127.0.0.1에서만 열려 있고 앞단 프록시(Caddy)가 X-Forwarded-For를 직접 채운다. 프록시를 거친 요청만 그 값을 믿는다.
            ip = self.client_address[0]
            forwarded = self.headers.get('X-Forwarded-For', '')
            if ip in ('127.0.0.1', '::1') and forwarded:
                return forwarded.split(',')[-1].strip() or ip
            return ip

        def worker_authorized(self):
            if broker is None or not broker.enabled():
                self.respond(404, {'error': '찾을 수 없는 페이지입니다.'})
                return False
            if not broker.check_token(self.headers.get('Authorization')):
                self.respond(401, {'error': '인증이 필요합니다.'})
                return False
            return True

        def session_token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
                old = cookie['curri_session'].value if 'curri_session' in cookie else None
            except CookieError:
                old = None
            self.token = store.session(old)
            return self.token

        def respond(self, status, body, mime='application/json; charset=utf-8'):
            content = json.dumps(body, ensure_ascii=False).encode() if mime.startswith('application/json') else body
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if hasattr(self, 'token'):
                cookie = f'curri_session={self.token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000'
                if secure_cookie:
                    cookie += '; Secure'
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(content)

        def snapshot(self):
            data = store.snapshot(self.token)
            for row in data['explorations']:
                try:
                    row['lab'] = catalog.card(row['lab_id'])
                except KeyError:
                    row['lab'] = None
            data['unread'] = community.unread(self.token) if data['user'] else 0
            return data

        def fail(self, exc):
            if isinstance(exc, LoginRequired):
                return self.respond(401, {'error': str(exc), 'code': 'login_required'})
            if isinstance(exc, InvalidCredentials):
                return self.respond(401, {'error': str(exc), 'code': 'invalid_credentials'})
            if isinstance(exc, ProfileRequired):
                return self.respond(403, {'error': str(exc), 'code': 'profile_required'})
            if isinstance(exc, NotFound):
                return self.respond(404, {'error': str(exc)})
            if isinstance(exc, MeetingLinkError):
                return self.respond(502, {'error': str(exc), 'code': 'meeting_link_failed'})
            if isinstance(exc, KeyError):
                return self.respond(404, {'error': '탐색할 수 있는 연구실을 찾지 못했습니다.'})
            if isinstance(exc, (ValueError, UnicodeDecodeError)):
                return self.respond(400, {'error': str(exc) if not isinstance(exc, json.JSONDecodeError) else 'JSON 입력이 올바르지 않습니다.'})
            # No credentials, body contents or local paths in the public error.
            print(f'curri request error: {type(exc).__name__}', flush=True)
            return self.respond(500, {'error': '요청을 처리하지 못했습니다. 입력을 유지한 채 다시 시도해 주세요.'})

        def do_GET(self):
            url = urlsplit(self.path)
            path, query = url.path, {k: v[0] for k, v in parse_qs(url.query).items()}
            if path == '/api/worker/poll':
                if not self.worker_authorized():
                    return
                try:
                    wait = float(query.get('wait', '20'))
                except ValueError:
                    wait = 20.0
                return self.respond(200, {'job': broker.poll(wait)})
            if path == '/api/engine':
                return self.respond(200, {'embedding': bool(broker and broker.available())})
            if path == '/api/session':
                self.session_token()
                return self.respond(200, self.snapshot())
            reads = {'/api/concepts': lambda: {'concepts': community.concepts},
                     '/api/community': lambda: community.lab_community(self.token, query.get('lab_id')),
                     '/api/reviews': lambda: community.board(self.token),
                     '/api/inbox': lambda: community.inbox(self.token),
                     '/api/thread': lambda: community.thread(self.token, int(query['id']) if query.get('id', '').isdigit() else None)}
            if path in reads:
                self.session_token()
                try:
                    return self.respond(200, reads[path]())
                except Exception as exc:
                    return self.fail(exc)
            allowed = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
            if path in allowed:
                name, mime = allowed[path]
                f = STATIC / name
                if f.exists():
                    return self.respond(200, f.read_bytes(), mime)
            self.respond(404, {'error': '찾을 수 없는 페이지입니다.'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if (origin and urlsplit(origin).netloc != self.headers.get('Host')) or self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return self.respond(403, {'error': '같은 사이트에서 다시 요청해 주세요.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.respond(415, {'error': 'JSON 요청만 지원합니다.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    return self.respond(413, {'error': '입력 크기를 확인해 주세요.'})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('입력 형식을 확인해 주세요.')
                path = urlsplit(self.path).path
                if path == '/api/worker/answer':
                    if not self.worker_authorized():
                        return
                    accepted = broker.answer(body.get('job_id'), body.get('lab_ids'), body.get('sims'), body.get('best'))
                    return self.respond(200, {'accepted': accepted})
                self.session_token()
                if path == '/api/search':
                    interests = body.get('interests')
                    goal = body.get('goal', 'explore')
                    if not isinstance(interests, str) or not 2 <= len(interests.strip()) <= 500 or goal not in ('explore', 'research', 'graduate'):
                        raise ValueError('관심이나 고민을 2~500자로 입력해 주세요.')
                    store.set_profile(self.token, {'interests': interests.strip(), 'goal': goal})
                    if engine is None:
                        return self.respond(200, {'labs': catalog.search(interests)})
                    ip = self.client_ip()
                    with lock:
                        recent = searches[ip]
                        while recent and recent[0] < time.time() - 60:
                            recent.popleft()
                        if len(recent) >= 20:
                            return self.respond(429, {'error': '검색 요청이 많습니다. 잠시 후 다시 시도해 주세요.'})
                        recent.append(time.time())
                    found = engine.search(interests.strip())
                    found.pop('reasons', None)
                    return self.respond(200, found)
                if path in ('/api/register', '/api/login'):
                    email, password = body.get('email'), body.get('password')
                    if not isinstance(email, str) or not isinstance(password, str):
                        raise ValueError('이메일과 비밀번호를 입력해 주세요.')
                    ip = self.client_ip()
                    with lock:
                        recent = attempts[ip]
                        while recent and recent[0] < time.time() - 300:
                            recent.popleft()
                        if len(recent) >= 15:
                            return self.respond(429, {'error': '로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.'})
                        recent.append(time.time())
                    register = path.endswith('register')
                    nickname, account = community.clean_account(body.get('account')) if register else (None, None)
                    self.token = store.authenticate(self.token, email, password, register=register, nickname=nickname, account=account)
                    return self.respond(200, self.snapshot())
                if path == '/api/logout':
                    self.token = store.logout(self.token)
                    return self.respond(200, self.snapshot())
                if path == '/api/account':
                    community.update_account(self.token, body)
                    return self.respond(200, self.snapshot())
                writes = {'/api/review': community.save_review, '/api/review/delete': community.delete_review,
                          '/api/contact': community.contact, '/api/reply': community.reply, '/api/meeting/request': community.request_meeting,
                          '/api/meeting/confirm': community.confirm_meeting, '/api/meeting/cancel': community.cancel_meeting}
                if path in writes:
                    return self.respond(200, writes[path](self.token, body))
                if path not in ('/api/explore', '/api/guide', '/api/save'):
                    return self.respond(404, {'error': '찾을 수 없는 요청입니다.'})
                lab_id = body.get('lab_id')
                if not isinstance(lab_id, str):
                    raise ValueError('연구실을 선택해 주세요.')
                canonical = catalog.resolve(lab_id)
                if path == '/api/explore':
                    detail = catalog.detail(canonical)
                    store.open_lab(self.token, canonical)
                    existing = next((r for r in store.snapshot(self.token)['explorations'] if r['lab_id'] == canonical), None)
                    if existing is None:
                        store.save_exploration(self.token, canonical, [], None, '', False)
                    else:
                        # A selection saved under an older course list may name courses no longer offered for this lab.
                        related = {c['id'] for c in detail['courses']}
                        kept = [x for x in existing.get('selected_ids', []) if x in related]
                        dropped = len(existing.get('selected_ids', [])) - len(kept)
                        if dropped:
                            store.save_exploration(self.token, canonical, kept, None, existing.get('note', ''), existing.get('saved', False))
                            existing = {**existing, 'selected_ids': kept, 'guide': None, 'stale_selection_dropped': dropped}
                    return self.respond(200, {'lab': detail, 'exploration': existing})
                selected = body.get('selected_ids', [])
                # Validate course IDs before allocating an anonymous exploration.
                if not isinstance(selected, list) or len(selected) > len(catalog.courses) or any(not isinstance(x, str) for x in selected):
                    raise ValueError('수강 과목 선택을 확인해 주세요.')
                related = {c['id'] for c in catalog.detail(canonical)['courses']}
                if any(x not in related for x in selected):
                    raise ValueError('제시된 연관 과목만 선택할 수 있습니다.')
                store.open_lab(self.token, canonical)
                existing = next((r for r in store.snapshot(self.token)['explorations'] if r['lab_id'] == canonical), {})
                if path == '/api/guide':
                    guide = catalog.guide(canonical, selected)
                    store.save_exploration(self.token, canonical, selected, guide, existing.get('note', ''), existing.get('saved', False))
                    return self.respond(200, {'guide': guide})
                note, saved = body.get('note', ''), body.get('saved', False)
                if not isinstance(note, str) or len(note) > 2000 or not isinstance(saved, bool):
                    raise ValueError('메모는 2,000자 이내로 입력해 주세요.')
                guide = existing.get('guide') if set(existing.get('selected_ids', [])) == set(selected) else None
                store.save_exploration(self.token, canonical, selected, guide, note, saved)
                return self.respond(200, {'ok': True})
            except Exception as exc:
                self.fail(exc)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
