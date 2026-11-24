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
from curri.curated_query_engine import CuratedQueryEngine
from curri.platform import Platform
from curri.server import make_server
from curri.store import Store

DATA = Path(__file__).resolve().parents[1] / 'data' / 'sunwoo'
CONSENTS = {'terms': True, 'privacy': True, 'age14': True}
ACCOUNT = {'real_name': '홍길동', 'nickname': '길동', 'school': 'POSTECH', 'interest_text': '로봇과 컴퓨터 비전'}
CATALOG = CuratedCatalog(DATA) if (DATA / 'app_profiles.jsonl').exists() else None


@unittest.skipUnless(CATALOG, 'curated data is needed')
class PlatformBase(unittest.TestCase):
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
        self.server = make_server('127.0.0.1', 0, self.catalog, self.store, community=self.community, platform=self.platform,
                                  engine=CuratedQueryEngine(self.catalog))
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


@unittest.skipUnless(CATALOG, 'curated data is needed')
class PlatformTests(PlatformBase):
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

    def test_lab_brief_keeps_sourced_topics_and_picks_cited_papers_in_code(self):
        call = self.client()
        call('/api/session')
        self.platform.llm.last_poll = time.time()
        status, body = call(f'/api/summary?lab_id={self.lab}')
        self.assertEqual((status, body['status']), (200, 'queued'))
        self.assertTrue(all(p['cited_by_count'] >= 10 for p in body['cited']['papers']))
        job = self.platform.llm.poll(0)
        self.assertEqual(job['kind'], 'summary')
        result = {'lab_oneliner': '로봇 파지를 연구해요.', 'papers': [],
                  'focus': [{'title': '로봇 파지', 'plain': '물체를 집는 방법', 'source_ids': ['S1', 'S1']},
                            {'title': '지어낸 주제', 'plain': '근거 없음', 'source_ids': ['S99']}]}
        self.assertEqual(self.platform.llm.answer({'job_id': job['id'], 'ok': True, 'result': result})['status'], 'done')
        brief = call(f'/api/summary?lab_id={self.lab}')[1]['summary']
        kind = self.platform.guide.brief_sources(self.lab)[0]['kind']
        self.assertEqual([(f['title'], f['basis']) for f in brief['focus']], [('로봇 파지', kind if kind == '연구실 소개' else f'{kind} 1개')])
    def test_a_reviewed_paper_decision_rebuilds_only_that_labs_brief(self):
        from curri.llm_jobs import cache_key
        from curri.research_guide import LabPapers, ResearchGuide, SUMMARY_VERSION
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'id': 'as_collected', 'basis': 'lab_led', 'papers': [{'openalex_id': 'W1', 'title': 'A'}]},
                    {'id': 'reviewed', 'basis': 'official_allowlist', 'papers': [{'openalex_id': 'W2', 'title': 'B', 'ownership_verification': {}}]},
                    {'id': 'emptied', 'basis': 'unverified_after_exclusions', 'papers': []}]
            (root / 'papers.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            guide = ResearchGuide(None, LabPapers(root / 'papers.jsonl'))
            # Labs as collected keep the key their cached brief was stored under.
            self.assertEqual(guide.summary_key('as_collected'), cache_key('summary', SUMMARY_VERSION, 'as_collected'))
            self.assertEqual(guide.summary_key('unknown'), cache_key('summary', SUMMARY_VERSION, 'unknown'))
            before = guide.summary_key('reviewed')
            self.assertNotEqual(before, cache_key('summary', SUMMARY_VERSION, 'reviewed'))
            self.assertNotEqual(guide.summary_key('emptied'), cache_key('summary', SUMMARY_VERSION, 'emptied'))
            rows[1]['papers'].append({'openalex_id': 'W3', 'title': 'C', 'ownership_verification': {}})
            (root / 'papers.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            self.assertNotEqual(ResearchGuide(None, LabPapers(root / 'papers.jsonl')).summary_key('reviewed'), before)

    def test_cited_papers_skip_namesakes_and_uncited_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = lambda title, cites, led=True, year=2020: {'title': title, 'cited_by_count': cites, 'lab_led': led, 'year': year, 'openalex_id': 'W1'}
            row = {'id': 'lab', 'papers': [paper('New', 2, year=2026), paper('Old classic', 120, year=2015), paper('Shared', 300, led=False),
                                           paper('Namesake', 900), paper('Solid', 40)]}
            (root / 'papers.jsonl').write_text(json.dumps(row) + '\n')
            (root / 'suspect_papers.json').write_text(json.dumps({'labs': {'lab': [{'title': 'Namesake'}]}}))
            from curri.research_guide import LabPapers
            cited = LabPapers(root / 'papers.jsonl').cited('lab')
        self.assertEqual([p['title'] for p in cited['papers']], ['Old classic', 'Solid', 'Shared'])
        self.assertIn('수집한 논문 4편(2015–2026년)', cited['note'])

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


@unittest.skipUnless(CATALOG, 'curated data is needed')
class FeedbackLoopTests(PlatformBase):
    def search(self, call, text='로봇 비전 연구'):
        return call('/api/search', {'interests': text, 'goal': 'explore'})[1]

    def test_result_votes_and_saves_rerank_the_same_query_for_feedback_arm(self):
        from curri.feedback import query_key
        target = None
        for i in range(4):
            call = self.client()
            call('/api/session')
            found = self.search(call)
            labs = [c['id'] for c in found['labs']]
            target = target or labs[-1]                   # the engine's last result
            self.assertEqual(call('/api/feedback', {'kind': 'result', 'lab_id': target, 'rank': len(labs) - 1, 'helpful': True})[0], 200)
            call('/api/explore', {'lab_id': target, 'rank': len(labs) - 1, 'from': 'results'})
            call('/api/save', {'lab_id': target, 'selected_ids': [], 'note': '', 'saved': True})
        key = query_key(found['interpretation']['likes'])
        scores, evidence = self.platform.feedback.lab_scores(key)
        self.assertGreater(evidence, 4)
        reranked, applied = self.platform.feedback.rerank(key, found['labs'])
        self.assertTrue(applied)
        self.assertLess([c['id'] for c in reranked].index(target), len(labs) - 1)
        self.assertTrue(reranked[[c['id'] for c in reranked].index(target)].get('social'))
        # the evaluation set now holds this query
        self.assertIn(key, self.platform.feedback.judgments())
        self.assertEqual(self.platform.feedback.evaluate(lambda text: labs)['queries'], 1)

    def test_down_votes_need_a_reason_and_feed_expansion_candidates(self):
        call = self.client()
        call('/api/session')
        found = self.search(call, '드론제어 연구')
        self.assertEqual(call('/api/feedback', {'kind': 'result', 'lab_id': self.lab, 'helpful': False, 'reasons': ['bogus']})[0], 400)
        self.assertEqual(call('/api/feedback', {'kind': 'result', 'lab_id': self.lab, 'helpful': False, 'reasons': ['off_topic']})[0], 200)
        self.assertEqual(call('/api/feedback', {'kind': 'search', 'rating': 1, 'comment': '드론 제어 연구실이 없어요'})[0], 200)
        status, view = self.admin('GET', 'feedback')
        self.assertEqual(status, 200)
        self.assertEqual(view['by_kind']['result']['down'], 1)
        self.assertIn('드론제어', [c['word'] for c in view['candidates']])
        self.assertEqual(view['comments'][0]['comment'], '드론 제어 연구실이 없어요')
        self.assertEqual(self.admin('POST', 'expansions/add', {'term': '드론제어', 'variants': 'drone control, uav control'})[0], 200)
        from curri.curated_catalog import EXPANSIONS
        self.assertIn('drone control', EXPANSIONS['드론제어'])
        self.assertEqual(self.admin('POST', 'feedback/status', {'id': view['comments'][0]['id'], 'status': 'done'})[0], 200)

    def test_service_and_meeting_feedback_rules(self):
        call = self.client()
        call('/api/session')
        self.assertEqual(call('/api/feedback', {'kind': 'service', 'rating': 4, 'comment': '좋아요'})[0], 200)
        self.assertEqual(call('/api/feedback', {'kind': 'service'})[0], 400)          # rating required
        self.register(call)
        self.assertEqual(call('/api/feedback', {'kind': 'meeting', 'ref_id': 999, 'rating': 5})[0], 400)  # not my ended meeting
        self.assertEqual(call('/api/feedback/pending')[1], {'meetings': []})

    def test_guide_retry_sends_previous_topics_and_reasons(self):
        call = self.client()
        call('/api/session')
        self.search(call, '로봇이 물체를 집는 비전')
        call('/api/explore', {'lab_id': self.lab})
        self.platform.llm.last_poll = time.time()
        call('/api/guide', {'lab_id': self.lab, 'selected_ids': []})
        job = self.platform.llm.poll(0)
        quote = self.platform.guide.sources(self.lab)[0]['text']
        topic = {'title': '첫 주제', 'question': '?', 'interest_link': '', 'lab_basis': {'source_id': 'S1', 'quote': quote}, 'course_basis': [], 'gaps': [], 'first_step': 'x', 'difficulty': '입문'}
        self.platform.llm.answer({'job_id': job['id'], 'ok': True, 'result': {'topics': [topic, topic], 'next_courses': [], 'caution': ''}})
        call(f'/api/guide/status?lab_id={self.lab}')
        self.assertEqual(call('/api/guide/feedback', {'lab_id': self.lab, 'helpful': False, 'topic': 0, 'reasons': ['too_hard']})[0], 200)
        status, body = call('/api/guide/retry', {'lab_id': self.lab, 'reasons': ['too_hard'], 'comment': '더 쉬운 것'})
        self.assertEqual((status, body['guide']['ai']['status']), (200, 'queued'))
        retry = self.platform.llm.poll(0)
        self.assertIn('첫 주제', retry['prompt'])
        self.assertIn('너무 어려워요', retry['prompt'])
        self.assertIn('더 쉬운 것', retry['prompt'])
