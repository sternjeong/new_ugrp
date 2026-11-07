"""Local JSON API; all exploration authorization is enforced server-side."""
from collections import defaultdict, deque
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit, parse_qs
from . import errors
from .community import Community, NotFound
from .llm_jobs import cache_key
from .meeting_links import MeetingLinkError
from .platform import Platform
from .privacy import consent_notice, policy
from .research_guide import PROMPT_VERSION, SUMMARY_VERSION
from .store import LoginRequired, InvalidCredentials, ProfileRequired

STATIC = Path(__file__).parent / 'static'
# Screens the single-page app can open directly from a shared link or a mail.
APP_PATHS = re.compile(r'^/(?:lab/[A-Za-z0-9:_. %-]{1,80}|results|saved|board|inbox|profile|privacy|reset|graduate|unsubscribe)?$')
ASSETS = {'/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/platform.js': ('platform.js', 'text/javascript; charset=utf-8'),
          '/styles.css': ('styles.css', 'text/css; charset=utf-8')}


def make_server(host, port, catalog, store, secure_cookie=False, community=None, engine=None, broker=None,
                research_papers=None, guide_variant_file=None, platform=None):
    attempts = defaultdict(deque)
    searches = defaultdict(deque)
    community = community or Community(store, catalog)
    P = platform or Platform(store, catalog, broker=broker)
    lock = threading.Lock()
    remote_aware = engine is not None and 'allow_remote' in inspect.signature(engine.search).parameters

    def limited(bucket, key, count, seconds):
        with lock:
            recent = bucket[key]
            while recent and recent[0] < time.time() - seconds:
                recent.popleft()
            if len(recent) >= count:
                return True
            recent.append(time.time())
        return False

    def guide_variant():
        if not research_papers or not guide_variant_file:
            return 'A'
        try:
            variant = Path(guide_variant_file).read_text(encoding='utf-8').strip().upper()
        except FileNotFoundError:
            return 'A'
        return variant if variant in ('A', 'B') else 'A'

    def ai_view(job):
        if job is None:
            return {'status': 'unavailable'}
        if job['status'] == 'done':
            return {'status': 'done', **job['result']}
        return {'status': job['status'], 'job_id': job['id']}

    def attach_ai_guide(token, lab_id, selected, guide):
        """Method R: queue (or reuse) a Sonnet guide for this lab, interest and course selection."""
        arm = P.events.arm(token, 'guide')
        guide['arm'] = arm
        if arm != 'R' or not P.llm.enabled():
            return
        if not P.accounts.overseas_allowed(token):
            guide['ai'] = {'status': 'no_consent'}
            return
        snap = store.snapshot(token)
        account = (snap['user'] or {}).get('account', {})
        student = {k: account.get(k) for k in ('department', 'grade', 'goal')}
        interests = snap['profile'].get('interests', '')
        key = cache_key('guide', PROMPT_VERSION, lab_id, interests, sorted(selected), student)
        job = P.llm.get(key=key)
        if job is None or job['status'] == 'failed':
            if not P.llm.online():
                guide['ai'] = {'status': 'offline'}
                return
            job = P.llm.submit('guide', key, P.guide.payload(lab_id, interests, selected, student))
        guide['ai'] = ai_view(job)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'Curri/0.2'

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

        def llm_authorized(self):
            if not P.llm.enabled():
                self.respond(404, {'error': '찾을 수 없는 페이지입니다.'})
                return False
            if not P.llm.check_token(self.headers.get('Authorization')):
                self.respond(401, {'error': '인증이 필요합니다.'})
                return False
            return True

        def admin_authorized(self):
            """Only through the admin VM's SSH tunnel: loopback peer, no public-proxy header, valid bearer token."""
            tunnel = self.client_address[0] in ('127.0.0.1', '::1') and not self.headers.get('X-Forwarded-For')
            if not P.admin.enabled() or not tunnel:
                self.respond(404, {'error': '찾을 수 없는 페이지입니다.'})
                return False
            if not P.admin.authorized(self.headers.get('Authorization')):
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

        def member(self):
            session = store.get_session(self.token)
            return bool(session and session['user_id'])

        def event(self, name, props=None):
            try:
                P.events.record(self.token, name, props, self.member())
            except Exception as exc:  # metrics must never break a request
                print(f'event error: {type(exc).__name__}', flush=True)

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
            data['overseas'] = P.accounts.overseas_allowed(self.token)
            data['features'] = {'ai_guide': P.llm.enabled(), 'ai_online': P.llm.online(), 'mail': P.mailer.enabled}
            if data['user']:
                session = store.get_session(self.token)
                data['user']['consent'] = P.accounts.consent_state(session['user_id'])
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
            errors.record(f'{self.command} {urlsplit(self.path).path}', exc)
            return self.respond(500, {'error': '요청을 처리하지 못했습니다. 입력을 유지한 채 다시 시도해 주세요.'})

        # ---- reads that need more than one call ----
        def summary(self, lab_id):
            lab_id = catalog.resolve(lab_id or '')
            key = cache_key('summary', SUMMARY_VERSION, lab_id)
            job = P.llm.get(key=key)
            if (job is None or job['status'] == 'failed') and P.llm.online():
                payload = P.guide.summary_payload(lab_id)  # public abstracts only; no personal data leaves the server
                job = P.llm.submit('summary', key, payload) if payload else None
            if job and job['status'] == 'done':
                return {'status': 'done', 'summary': job['result']}
            return {'status': job['status'] if job else ('offline' if P.llm.enabled() else 'unavailable')}

        def guide_status(self, lab_id):
            lab_id = catalog.resolve(lab_id or '')
            existing = next((r for r in store.snapshot(self.token)['explorations'] if r['lab_id'] == lab_id), None)
            guide = existing and existing.get('guide')
            ai = (guide or {}).get('ai') or {}
            if ai.get('status') in ('queued', 'running') and ai.get('job_id'):
                job = P.llm.get(job_id=ai['job_id'])
                fresh = ai_view(job)
                if fresh['status'] != ai['status']:
                    guide['ai'] = fresh
                    store.save_exploration(self.token, lab_id, existing['selected_ids'], guide, existing.get('note', ''), existing.get('saved', False))
                    if fresh['status'] in ('done', 'failed'):
                        self.event('guide_ready' if fresh['status'] == 'done' else 'guide_failed', {'arm': guide.get('arm', 'R')})
            return {'guide': guide}

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
            if path == '/api/llm/poll':
                if not self.llm_authorized():
                    return
                try:
                    wait = float(query.get('wait', '25'))
                except ValueError:
                    wait = 25.0
                return self.respond(200, {'job': P.llm.poll(wait)})
            if path.startswith('/api/admin/'):
                if not self.admin_authorized():
                    return
                try:
                    if path == '/api/admin/backup':
                        P.admin.audit(self.headers.get('X-Admin-User'), 'GET backup', {})
                        return self.respond(200, P.admin.backup_bytes(), 'application/octet-stream')
                    return self.respond(200, P.admin.handle('GET', path[len('/api/admin/'):], query, self.headers.get('X-Admin-User')))
                except Exception as exc:
                    return self.fail(exc)
            if path == '/api/engine':
                return self.respond(200, {'embedding': bool(broker and broker.available())})
            if path == '/api/session':
                self.session_token()
                return self.respond(200, self.snapshot())
            reads = {'/api/concepts': lambda: {'concepts': community.concepts},
                     '/api/community': lambda: community.lab_community(self.token, query.get('lab_id')),
                     '/api/reviews': lambda: community.board(self.token),
                     '/api/inbox': lambda: community.inbox(self.token),
                     '/api/thread': lambda: community.thread(self.token, int(query['id']) if query.get('id', '').isdigit() else None),
                     '/api/privacy': lambda: {'policy': policy(P.privacy_slots), 'consent': consent_notice()},
                     '/api/labs': lambda: {'labs': sorted(({'id': lid, 'professors': p['professors'], 'name': p.get('lab_name', ''),
                                                            'department': p.get('department', '')} for lid, p in catalog.profiles.items()),
                                                           key=lambda x: (x['department'], x['professors'][0] or ''))},
                     '/api/qna': lambda: P.qna.list(self.token, query.get('lab_id')),
                     '/api/watch': lambda: P.watch.state(self.token, catalog.resolve(query.get('lab_id') or '')),
                     '/api/summary': lambda: self.summary(query.get('lab_id')),
                     '/api/guide/status': lambda: self.guide_status(query.get('lab_id'))}
            if path in reads:
                self.session_token()
                try:
                    return self.respond(200, reads[path]())
                except Exception as exc:
                    return self.fail(exc)
            if APP_PATHS.match(path) and (STATIC / 'index.html').exists():
                return self.respond(200, (STATIC / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path in ASSETS:
                name, mime = ASSETS[path]
                f = STATIC / name
                if f.exists():
                    return self.respond(200, f.read_bytes(), mime)
            self.respond(404, {'error': '찾을 수 없는 페이지입니다.'})

        def do_POST(self):
            path = urlsplit(self.path).path
            internal = path in ('/api/worker/answer', '/api/llm/answer') or path.startswith('/api/admin/')
            origin = self.headers.get('Origin')
            if not internal and ((origin and urlsplit(origin).netloc != self.headers.get('Host')) or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                return self.respond(403, {'error': '같은 사이트에서 다시 요청해 주세요.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.respond(415, {'error': 'JSON 요청만 지원합니다.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= (262144 if internal else 65536):
                    return self.respond(413, {'error': '입력 크기를 확인해 주세요.'})
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('입력 형식을 확인해 주세요.')
                if path == '/api/worker/answer':
                    if not self.worker_authorized():
                        return
                    accepted = broker.answer(body.get('job_id'), body.get('lab_ids'), body.get('sims'), body.get('best'))
                    return self.respond(200, {'accepted': accepted})
                if path == '/api/llm/answer':
                    if not self.llm_authorized():
                        return
                    return self.respond(200, P.llm.answer(body))
                if path.startswith('/api/admin/'):
                    if not self.admin_authorized():
                        return
                    return self.respond(200, P.admin.handle('POST', path[len('/api/admin/'):], body, self.headers.get('X-Admin-User')))
                self.session_token()
                if path == '/api/search':
                    interests = body.get('interests')
                    goal = body.get('goal', 'explore')
                    if not isinstance(interests, str) or not 2 <= len(interests.strip()) <= 500 or goal not in ('explore', 'research', 'graduate'):
                        raise ValueError('관심이나 고민을 2~500자로 입력해 주세요.')
                    profile = store.snapshot(self.token)['profile']
                    store.set_profile(self.token, {**{k: v for k, v in profile.items() if k == 'no_overseas'}, 'interests': interests.strip(), 'goal': goal})
                    if engine is None:
                        labs = catalog.search(interests)
                        self.event('search', {'mode': 'dictionary', 'n': len(labs)})
                        return self.respond(200, {'labs': labs})
                    if limited(searches, self.client_ip(), 20, 60):
                        return self.respond(429, {'error': '검색 요청이 많습니다. 잠시 후 다시 시도해 주세요.'})
                    found = (engine.search(interests.strip(), allow_remote=P.accounts.overseas_allowed(self.token)) if remote_aware
                             else engine.search(interests.strip()))
                    found.pop('reasons', None)
                    self.event('search', {'mode': found.get('mode', ''), 'n': len(found.get('labs', []))})
                    if found.get('intent') == 'search' and not found.get('labs'):
                        self.event('zero_results')
                        P.events.zero_query(interests.strip())
                    return self.respond(200, found)
                if path == '/api/prewarm':
                    # The student started typing: wake the embedding worker so the first search is less likely to wait.
                    started = False
                    if engine is not None and getattr(engine, 'launcher', None) and broker and not broker.available() \
                            and P.accounts.overseas_allowed(self.token) and not limited(searches, 'prewarm:' + self.client_ip(), 3, 600):
                        started = engine.launcher.ensure_started()
                    return self.respond(200, {'started': bool(started), 'embedding': bool(broker and broker.available())})
                if path in ('/api/register', '/api/login'):
                    email, password = body.get('email'), body.get('password')
                    if not isinstance(email, str) or not isinstance(password, str):
                        raise ValueError('이메일과 비밀번호를 입력해 주세요.')
                    if limited(attempts, self.client_ip(), 15, 300):
                        return self.respond(429, {'error': '로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.'})
                    register = path.endswith('register')
                    nickname, account = community.clean_account(body.get('account')) if register else (None, None)
                    consents = P.accounts.clean_consents(body) if register else None
                    self.token = store.authenticate(self.token, email, password, register=register, nickname=nickname, account=account)
                    if register:
                        P.accounts.record_consent(store.current_user(self.token)['id'], consents)
                        self.event('register')
                    return self.respond(200, self.snapshot())
                if path == '/api/logout':
                    self.token = store.logout(self.token)
                    return self.respond(200, self.snapshot())
                if path == '/api/account':
                    community.update_account(self.token, body)
                    return self.respond(200, self.snapshot())
                if path == '/api/password/forgot':
                    if limited(attempts, 'forgot:' + self.client_ip(), 5, 3600):
                        return self.respond(429, {'error': '요청이 많습니다. 잠시 후 다시 시도해 주세요.'})
                    return self.respond(200, P.accounts.forgot_password(body))
                if path == '/api/password/reset':
                    if limited(attempts, 'reset:' + self.client_ip(), 10, 3600):
                        return self.respond(429, {'error': '요청이 많습니다. 잠시 후 다시 시도해 주세요.'})
                    return self.respond(200, P.accounts.reset_password(body))
                if path == '/api/account/delete':
                    result = P.accounts.delete_account(self.token, body)
                    self.token = store.session(None)
                    return self.respond(200, {**result, 'session': self.snapshot()})
                if path == '/api/account/overseas':
                    P.accounts.set_overseas(self.token, body.get('allowed'))
                    return self.respond(200, self.snapshot())
                if path in ('/api/report', '/api/event', '/api/guide/feedback'):
                    if path == '/api/event':
                        if body.get('name') not in ('result_open', 'summary_view'):
                            raise ValueError('기록할 수 없는 이벤트입니다.')
                        self.event(body['name'], body.get('props') if isinstance(body.get('props'), dict) else None)
                        return self.respond(200, {'ok': True})
                    if path == '/api/guide/feedback':
                        if not isinstance(body.get('helpful'), bool) or not isinstance(body.get('lab_id'), str):
                            raise ValueError('피드백을 확인해 주세요.')
                        self.event('guide_feedback', {'helpful': body['helpful'], 'topic': int(body.get('topic', 0)) if str(body.get('topic', 0)).isdigit() else 0,
                                                      'lab': catalog.resolve(body['lab_id'])[:40]})
                        return self.respond(200, {'ok': True})
                    return self.respond(200, P.events.report(store.current_user(self.token)['id'], body))
                platform_writes = {
                    '/api/email/send': P.accounts.send_verification, '/api/email/verify': P.accounts.verify_email,
                    '/api/account/notify': P.accounts.set_notify, '/api/graduate/apply': P.accounts.apply_graduate,
                    '/api/graduate/settings': P.accounts.update_graduate, '/api/block': P.accounts.block,
                    '/api/qna/ask': P.qna.ask, '/api/qna/answer': P.qna.answer, '/api/qna/delete': P.qna.delete,
                    '/api/watch': P.watch.toggle}
                if path in platform_writes:
                    if path in ('/api/email/send',) and limited(attempts, 'mail:' + self.client_ip(), 10, 3600):
                        return self.respond(429, {'error': '요청이 많습니다. 잠시 후 다시 시도해 주세요.'})
                    result = platform_writes[path](self.token, body)
                    names = {'/api/qna/ask': 'qna_ask', '/api/qna/answer': 'qna_answer', '/api/watch': 'watch', '/api/graduate/apply': 'graduate_apply'}
                    if path in names:
                        self.event(names[path])
                    return self.respond(200, result)
                if path == '/api/coffeechat':
                    # One request from the lab page: the first message, optionally with proposed meeting times.
                    if body.get('share_consent') is not True:
                        raise ValueError('선배에게 이름·이메일·프로필이 전달되는 것에 동의해 주세요.')
                    started = community.contact(self.token, body)
                    meeting = body.get('meeting')
                    if isinstance(meeting, dict):
                        try:
                            community.request_meeting(self.token, {**meeting, 'thread_id': started['thread_id']})
                        except ValueError as exc:
                            return self.respond(200, {**started, 'meeting_error': str(exc)})
                    self.event('coffeechat', {'meeting': isinstance(meeting, dict)})
                    return self.respond(200, started)
                writes = {'/api/review': community.save_review, '/api/review/delete': community.delete_review,
                          '/api/contact': community.contact, '/api/reply': community.reply, '/api/meeting/request': community.request_meeting,
                          '/api/meeting/confirm': community.confirm_meeting, '/api/meeting/cancel': community.cancel_meeting}
                if path in writes:
                    if path == '/api/contact' and body.get('share_consent') is False:
                        raise ValueError('선배에게 이름·이메일·프로필이 전달되는 것에 동의해 주세요.')
                    result = writes[path](self.token, body)
                    names = {'/api/contact': 'contact', '/api/meeting/request': 'meeting_request', '/api/meeting/confirm': 'meeting_confirm'}
                    if path in names:
                        self.event(names[path])
                    return self.respond(200, result)
                if path not in ('/api/explore', '/api/guide', '/api/save'):
                    return self.respond(404, {'error': '찾을 수 없는 요청입니다.'})
                lab_id = body.get('lab_id')
                if not isinstance(lab_id, str):
                    raise ValueError('연구실을 선택해 주세요.')
                canonical = catalog.resolve(lab_id)
                if path == '/api/explore':
                    detail = catalog.detail(canonical)
                    variant = guide_variant()
                    if variant == 'B':
                        detail = {**detail, 'research_papers': research_papers.recent(canonical)}
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
                    if existing and existing.get('guide') and existing['guide'].get('variant', 'A') != variant:
                        existing = {**existing, 'guide': None}
                    if research_papers:
                        store.count_guide_event(variant, 'explore')
                    rank = body.get('rank')
                    self.event('explore', {'rank': rank if type(rank) is int else -1, 'from': str(body.get('from', ''))[:20]})
                    return self.respond(200, {'lab': detail, 'exploration': existing, 'guide_variant': variant})
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
                    variant = guide_variant()
                    if variant == 'B':
                        guide['research'] = research_papers.guide(canonical, body.get('paper_ids', []))
                        if guide['research']['selected']:
                            guide['start_now'] = [
                                {'title': p['title'], 'difficulty': '논문 탐색',
                                 'basis': '선택한 논문의 연구 문제와 방법을 살펴보세요.',
                                 'steps': ['초록에서 연구 문제와 사용한 방법을 찾아봅니다.',
                                           '선택한 과목의 내용과 연결할 수 있는 부분이 있는지 확인합니다.',
                                           '논문 원문에서 결과와 한계를 확인합니다.'],
                                 'evidence': [{'topic': p['id'], 'label': p['title'],
                                               'text': p['abstract'] or p['title'], 'urls': [p['url']],
                                               'section': 'paper', 'role': 'paper'}], 'courses': []}
                                for p in guide['research']['selected']]
                            guide['insufficient_evidence'] = False
                    guide['variant'] = variant
                    attach_ai_guide(self.token, canonical, selected, guide)
                    store.save_exploration(self.token, canonical, selected, guide, existing.get('note', ''), existing.get('saved', False))
                    if research_papers:
                        store.count_guide_event(variant, 'guide')
                    self.event('guide_request', {'arm': guide.get('arm') or '', 'ai': (guide.get('ai') or {}).get('status', '')})
                    if (guide.get('ai') or {}).get('status') == 'done':
                        self.event('guide_ready', {'arm': 'R', 'cached': True})
                    return self.respond(200, {'guide': guide})
                note, saved = body.get('note', ''), body.get('saved', False)
                if not isinstance(note, str) or len(note) > 2000 or not isinstance(saved, bool):
                    raise ValueError('메모는 2,000자 이내로 입력해 주세요.')
                guide = existing.get('guide') if set(existing.get('selected_ids', [])) == set(selected) else None
                store.save_exploration(self.token, canonical, selected, guide, note, saved)
                if saved and not existing.get('saved'):
                    self.event('save')
                return self.respond(200, {'ok': True})
            except Exception as exc:
                self.fail(exc)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.platform = P
    return server
