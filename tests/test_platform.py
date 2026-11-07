import http.cookiejar
import json
import re
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from curri.community import Community
from curri.curated_catalog import CuratedCatalog
from curri.platform import Platform
from curri.server import make_server
from curri.store import Store

DATA = Path(__file__).resolve().parents[1] / 'data' / 'sunwoo'
CONSENTS = {'terms': True, 'privacy': True, 'age14': True}
ACCOUNT = {'real_name': '홍길동', 'nickname': '길동', 'school': 'POSTECH', 'interest_text': '로봇과 컴퓨터 비전'}
CATALOG = CuratedCatalog(DATA) if (DATA / 'app_profiles.jsonl').exists() else None


@unittest.skipUnless(CATALOG, 'curated data is needed')
class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        local = root / 'local'
        local.mkdir()
        (local / 'admin_token').write_text('admin-secret-token')
        (local / 'llm_worker_token').write_text('llm-secret-token')
        self.store = Store(root / 'app.sqlite')
        self.catalog = CATALOG
        self.community = Community(self.store, self.catalog, seed=False)
        self.platform = Platform(self.store, self.catalog, DATA, local)
        self.server = make_server('127.0.0.1', 0, self.catalog, self.store, community=self.community, platform=self.platform)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.lab = next(l for l, p in self.catalog.profiles.items() if p['professors'][0] == '조민수')

    def client(self):
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def call(path, data=None, headers=None):
            h = {'Content-Type': 'application/json', 'Origin': self.url, **(headers or {})}
            req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=h)
            try:
                response = opener.open(req)
            except urllib.error.HTTPError as exc:
                response = exc
            payload = response.read()
            return response.status, json.loads(payload) if 'application/json' in response.headers.get('Content-Type', '') else payload
        return call

    def register(self, call, email='student@example.com', nickname='길동', consents=CONSENTS):
        return call('/api/register', {'email': email, 'password': 'valid-password', 'consents': consents, 'account': {**ACCOUNT, 'nickname': nickname}})

    def outbox(self, kind):
        with self.store.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM outbox WHERE kind=? ORDER BY id', (kind,))]

    def verify(self, call):
        call('/api/email/send', {})
        code = re.search(r'\d{6}', self.outbox('verify')[-1]['body']).group(0)
        return call('/api/email/verify', {'code': code})

    def admin(self, method, name, data=None, forwarded=False):
        headers = {'Authorization': 'Bearer admin-secret-token', 'Content-Type': 'application/json', 'X-Admin-User': 'tester'}
        if forwarded:
            headers['X-Forwarded-For'] = '1.2.3.4'
        req = urllib.request.Request(f'{self.url}/api/admin/{name}', data=json.dumps(data).encode() if method == 'POST' else None, headers=headers)
        try:
            response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    def test_registration_needs_required_consents_and_records_them(self):
        call = self.client()
        call('/api/session')
        status, body = self.register(call, consents={'terms': True, 'privacy': True})
        self.assertEqual(status, 400)
        self.assertIn('만 14세', body['error'])
        status, snap = self.register(call)
        self.assertEqual(status, 200)
        self.assertFalse(snap['overseas'])  # optional consent not given
        self.assertEqual(snap['user']['consent']['version'], '2026-11-07')
        status, snap = call('/api/account/overseas', {'allowed': True})
        self.assertTrue(snap['overseas'])
        status, privacy = call('/api/privacy')
        self.assertIn('【입력 필요', ' '.join(i for s in privacy['policy']['sections'] for i in s['items']))
        self.assertIn('Anthropic', json.dumps(privacy, ensure_ascii=False))

    def test_email_verification_and_password_reset(self):
        call = self.client()
        call('/api/session')
        self.register(call)
        self.assertEqual(self.verify(call), (200, {'verified': True}))
        self.assertTrue(call('/api/session')[1]['user']['email_verified'])
        other = self.client()
        other('/api/session')
        self.assertEqual(other('/api/password/forgot', {'email': 'nobody@example.com'}), (200, {'ok': True}))
        self.assertEqual(other('/api/password/forgot', {'email': 'student@example.com'}), (200, {'ok': True}))
        token = re.search(r'token=([\w-]+)', self.outbox('reset')[-1]['body']).group(1)
        self.assertEqual(other('/api/password/reset', {'token': token, 'password': 'another-password'})[0], 200)
        self.assertEqual(other('/api/password/reset', {'token': token, 'password': 'another-password'})[0], 400)  # single use
        self.assertEqual(other('/api/login', {'email': 'student@example.com', 'password': 'another-password'})[0], 200)

    def make_graduate(self, email='grad@postech.ac.kr', nickname='선배1', limit=1):
        call = self.client()
        call('/api/session')
        self.register(call, email, nickname)
        status, body = call('/api/graduate/apply', {'lab_id': self.lab, 'program': '석사과정', 'research': '로봇 파지', 'contact_consent': True, 'monthly_limit': limit})
        self.assertEqual(status, 400)  # email not verified yet
        self.verify(call)
        self.assertEqual(call('/api/graduate/apply', {'lab_id': self.lab, 'program': '석사과정', 'research': '로봇 파지',
                                                      'contact_consent': True, 'monthly_limit': limit, 'availability': '평일 저녁'})[1], {'grad_status': 'pending'})
        status, pending = self.admin('GET', 'graduates')
        uid = pending['pending'][-1]['id']
        self.assertEqual(self.admin('POST', 'graduates/decide', {'user_id': uid, 'approve': True})[0], 200)
        return call, uid

    def test_graduate_application_requires_school_mail_and_admin_approval(self):
        call = self.client()
        call('/api/session')
        self.register(call)
        self.verify(call)
        status, body = call('/api/graduate/apply', {'lab_id': self.lab, 'program': '석사과정', 'research': '로봇', 'contact_consent': True})
        self.assertEqual(status, 400)
        self.assertIn('postech.ac.kr', body['error'])
        grad, uid = self.make_graduate()
        self.assertEqual(grad('/api/session')[1]['user']['role'], 'graduate')
        student = self.client()
        student('/api/session')
        self.register(student, 's2@example.com', '학생2')
        card = next(g for g in student(f'/api/community?lab_id={self.lab}')[1]['graduates'] if g['id'] == uid)
        self.assertEqual((card['availability'], card['verified'], card['email']), ('평일 저녁', True, None))
        self.assertEqual(student('/api/coffeechat', {'graduate_id': uid, 'subject': '커피챗 요청', 'body': '로봇 파지 연구가 궁금합니다.'})[0], 400)  # consent
        status, started = student('/api/coffeechat', {'graduate_id': uid, 'subject': '커피챗 요청', 'body': '로봇 파지 연구가 궁금합니다.', 'share_consent': True,
                                                      'meeting': {'mode': 'online', 'minutes': 20, 'slots': [time.strftime('%Y-%m-%dT15:00', time.localtime(time.time() + 86400 * 3))]}})
        self.assertEqual(status, 200)
        self.assertNotIn('meeting_error', started)
        third = self.client()
        third('/api/session')
        self.register(third, 's3@example.com', '학생3')
        status, body = third('/api/contact', {'graduate_id': uid, 'subject': '질문', 'body': '연구참여 문의 드립니다.'})
        self.assertEqual(status, 400)  # monthly limit 1 reached
        self.assertIn('이번 달', body['error'])

    def test_account_deletion_anonymizes_messages_and_blocks_login(self):
        grad, uid = self.make_graduate(limit=5)
        student = self.client()
        student('/api/session')
        self.register(student)
        student('/api/contact', {'graduate_id': uid, 'subject': '안녕하세요', 'body': '연구참여 문의 드립니다.'})
        self.assertEqual(student('/api/account/delete', {'password': 'wrong-password'})[0], 400)
        status, body = student('/api/account/delete', {'password': 'valid-password'})
        self.assertEqual((status, body['deleted'], body['session']['user']), (200, True, None))
        thread = grad('/api/inbox')[1]['threads'][0]
        self.assertEqual(thread['other']['name'], '탈퇴한 사용자')
        self.assertEqual(self.client()('/api/login', {'email': 'student@example.com', 'password': 'valid-password'})[0], 401)

    def test_ai_guide_is_queued_answered_by_worker_and_validated(self):
        call = self.client()
        call('/api/session')
        call('/api/search', {'interests': '로봇이 물체를 집는 비전', 'goal': 'explore'})
        call('/api/explore', {'lab_id': self.lab})
        self.platform.llm.last_poll = time.time()  # a worker is online
        status, body = call('/api/guide', {'lab_id': self.lab, 'selected_ids': []})
        self.assertEqual((status, body['guide']['arm'], body['guide']['ai']['status']), (200, 'R', 'queued'))
        job = self.platform.llm.poll(0)
        self.assertEqual(job['kind'], 'guide')
        quote = self.platform.guide.sources(self.lab)[0]['text']
        topic = {'title': '대칭 기반 파지', 'question': '?', 'interest_link': '관심', 'lab_basis': {'source_id': 'S1', 'quote': quote},
                 'course_basis': [{'course_code': 'CSED233', 'concept': 'x', 'how_used': 'y'}], 'gaps': ['비전 기초'],
                 'first_step': '공개 데이터 10개를 고른다', 'difficulty': '입문'}
        fake = {'title': '지어낸 주제', 'question': '?', 'interest_link': '', 'lab_basis': {'source_id': 'S1', 'quote': '연구실에 없는 문장입니다 정말로'},
                'course_basis': [], 'gaps': [], 'first_step': '', 'difficulty': '입문'}
        result = {'topics': [topic, fake], 'next_courses': [{'course_code': 'NOPE000', 'reason': 'x'}], 'caution': '확인 필요'}
        self.assertEqual(self.platform.llm.answer({'job_id': job['id'], 'ok': True, 'result': result})['status'], 'done')
        guide = call(f'/api/guide/status?lab_id={self.lab}')[1]['guide']
        self.assertEqual(guide['ai']['status'], 'done')
        self.assertEqual([t['title'] for t in guide['ai']['topics']], ['대칭 기반 파지'])   # unverifiable topic dropped
        self.assertEqual(guide['ai']['topics'][0]['courses'], [])                          # course not marked by the student
        self.assertEqual(guide['ai']['next_courses'], [])                                 # course not offered
        self.assertEqual(call('/api/guide/feedback', {'lab_id': self.lab, 'helpful': True, 'topic': 0})[0], 200)
        # Worker endpoints need the worker token.
        self.assertEqual(self.client()('/api/llm/poll')[0], 401)

    def test_member_without_overseas_consent_gets_no_ai_guide(self):
        call = self.client()
        call('/api/session')
        self.register(call)
        self.platform.llm.last_poll = time.time()
        call('/api/explore', {'lab_id': self.lab})
        self.assertEqual(call('/api/guide', {'lab_id': self.lab, 'selected_ids': []})[1]['guide']['ai'], {'status': 'no_consent'})

    def test_anonymous_qna(self):
        grad, uid = self.make_graduate()
        student = self.client()
        student('/api/session')
        self.register(student)
        self.assertEqual(grad('/api/qna/ask', {'lab_id': self.lab, 'body': '선배도 질문할 수 있나요?'})[0], 400)
        status, listing = student('/api/qna/ask', {'lab_id': self.lab, 'body': '학부생은 주로 어떤 일을 하나요?'})
        qid = listing['question_id']
        status, listing = grad('/api/qna/answer', {'question_id': qid, 'body': '처음에는 논문 재현부터 해요.'})
        self.assertEqual(status, 200)
        public = self.client()('/api/qna?lab_id=' + self.lab)[1]
        q = public['questions'][0]
        self.assertEqual(q['author'], '익명 학생')
        self.assertNotIn('길동', json.dumps(q, ensure_ascii=False))
        self.assertTrue(q['answers'][0]['author'].startswith('석사과정'))
        other_lab = next(l for l in self.catalog.profiles if l != self.lab)
        student('/api/qna/ask', {'lab_id': other_lab, 'body': '다른 연구실 질문입니다.'})
        other_q = self.client()('/api/qna?lab_id=' + other_lab)[1]['questions'][0]['id']
        self.assertEqual(grad('/api/qna/answer', {'question_id': other_q, 'body': '답할 수 없어야 해요.'})[0], 400)
        self.assertEqual(student('/api/report', {'kind': 'answer', 'ref_id': q['answers'][0]['id'], 'reason': '부적절한 내용'})[0], 200)
        report = self.admin('GET', 'reports')[1]['reports'][0]
        self.admin('POST', 'reports/resolve', {'id': report['id'], 'action': 'hide'})
        self.assertEqual(self.client()('/api/qna?lab_id=' + self.lab)[1]['questions'][0]['answers'], [])

    def test_watch_finds_new_papers_and_mails_verified_watchers(self):
        call = self.client()
        call('/api/session')
        self.register(call)
        self.verify(call)
        self.assertEqual(call('/api/watch', {'lab_id': self.lab, 'on': True})[1], {'watching': True})
        self.platform.watch.fetch = lambda authors, since: [{'id': 'https://openalex.org/W999', 'title': '새 논문 제목', 'publication_year': 2026, 'doi': None}]
        self.assertEqual(self.platform.watch.run(), {self.lab: ['새 논문 제목']})
        self.assertEqual(self.platform.watch.run(), {})  # seen once
        self.assertEqual(call(f'/api/watch?lab_id={self.lab}')[1]['new_papers'][0]['title'], '새 논문 제목')
        self.assertIn('새 논문 제목', self.outbox('watch')[0]['body'])

    def test_notifier_mails_unread_messages_once(self):
        grad, uid = self.make_graduate(limit=5)
        self.verify(grad) if not grad('/api/session')[1]['user']['email_verified'] else None
        student = self.client()
        student('/api/session')
        self.register(student)
        student('/api/contact', {'graduate_id': uid, 'subject': '문의', 'body': '연구참여 문의 드립니다.'})
        later = time.time() + 300
        self.assertEqual(self.platform.notifier.run_once(later)['messages'], 1)
        self.assertEqual(self.platform.notifier.run_once(later)['messages'], 0)
        self.assertIn('문의', self.outbox('messages')[0]['body'])

    def test_admin_api_only_through_tunnel_with_token(self):
        self.assertEqual(self.admin('GET', 'overview', forwarded=True)[0], 404)
        req = urllib.request.Request(f'{self.url}/api/admin/overview')
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 401)
        status, overview = self.admin('GET', 'overview')
        self.assertEqual(status, 200)
        self.assertIn('funnel', overview['metrics'])
        self.admin('GET', 'users')
        self.assertEqual(self.admin('GET', 'audit')[1]['audit'][0]['action'], 'GET users')

    def test_events_funnel_and_app_paths(self):
        call = self.client()
        call('/api/session')
        call('/api/search', {'interests': '로봇 비전', 'goal': 'explore'})
        call('/api/explore', {'lab_id': self.lab, 'rank': 0, 'from': 'results'})
        funnel = {f['step']: f['sessions'] for f in self.platform.events.metrics()['funnel']}
        self.assertEqual((funnel['search'], funnel['explore']), (1, 1))
        status, html = call(f'/lab/{self.lab}')
        self.assertEqual(status, 200)
        self.assertIn(b'<html', html)
        self.assertEqual(call('/lab/../../etc/passwd')[0], 404)


if __name__ == '__main__':
    unittest.main()
