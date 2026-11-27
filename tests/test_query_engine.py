import http.cookiejar
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from curri.embed_broker import EmbedBroker, query_key
from curri.profile_catalog import ProfileCatalog
from curri.query_engine import QueryEngine, interpret, plan
from curri.server import make_server
from curri.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo' / 'legacy' / 'mvp-4dept'
QU = ROOT / 'experiments' / 'query_understanding'
TOKEN = 'test-token-0123456789'


class FakeWorker(threading.Thread):
    """Kaggle 워커 대역: 구절마다 정해진 유사도 행을 돌려준다. rows[구절] = {lab_id: 유사도}."""

    def __init__(self, broker, lab_ids, rows=None, default=0.4):
        super().__init__(daemon=True)
        self.broker, self.lab_ids, self.rows, self.default = broker, lab_ids, rows or {}, default
        self.stop = False
        self.seen = []

    def run(self):
        while not self.stop:
            job = self.broker.poll(0.2)
            if not job:
                continue
            self.seen.append(job['phrases'])
            sims = {p: [self.rows.get(p, {}).get(lid, self.default) for lid in self.lab_ids] for p in job['phrases']}
            best = {p: [0] * len(self.lab_ids) for p in job['phrases']}
            self.broker.answer(job['id'], self.lab_ids, sims, best)


@unittest.skipUnless((DATA / 'courses.jsonl').exists(), 'MVP course data is needed')
class QueryEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ProfileCatalog(DATA)
        cls.lab_ids = sorted(cls.catalog.profiles)

    def test_broker_returns_a_query_analysis_and_caches_it(self):
        broker = EmbedBroker(TOKEN)
        broker.last_poll = time.time()
        query = {'raw': '낯선 표현', 'text': '낯선 표현', 'dislikes': [], 'gate': 0.05}

        def answer():
            job = broker.poll(2)
            self.assertEqual(job['query'], query)
            broker.answer(job['id'], ['lab'], {'낯선 표현': [0.5]}, {'낯선 표현': [0]}, {'chunk': {'lab': 0.5}})
        threading.Thread(target=answer, daemon=True).start()
        found = broker.understand(['낯선 표현'], query, 3)
        self.assertEqual(found[query_key(query)], {'chunk': {'lab': 0.5}})
        broker.last_poll = 0
        self.assertEqual(broker.understand(['낯선 표현'], query, 0.1)[query_key(query)], {'chunk': {'lab': 0.5}})

    def test_broker_keeps_phrases_when_no_analysis_can_be_had(self):
        broker = EmbedBroker(TOKEN)
        broker.cache['구절'] = {'sims': {}, 'best': {}}
        found = broker.understand(['구절'], {'raw': '구절', 'text': '구절', 'dislikes': [], 'gate': 0.05}, 0.1, remote=False)
        self.assertEqual(list(found), ['구절'])

    def test_negation_and_phrase_are_interpreted(self):
        self.assertEqual(interpret('나는 로봇은 싫은데 컴퓨터 아키텍처는 좋아요'), {'likes': ['컴퓨터 아키텍처'], 'dislikes': ['로봇']})
        self.assertEqual(interpret('로봇보다는 컴퓨터구조가 좋아요'), {'likes': ['컴퓨터구조'], 'dislikes': ['로봇']})
        p = plan('나는 로봇은 싫은데 컴퓨터 아키텍처는 좋아요', self.catalog)
        self.assertEqual((p['intent'], p['likes'], p['dislikes']), ('search', ['컴퓨터 구조'], ['로봇']))   # 동의어 정규화

    def test_non_search_intents_return_a_message_and_no_labs(self):
        engine = QueryEngine(self.catalog)
        for text, intent in [('대학원을 가야 할지 모르겠어요', 'career'), ('유기화학 합성 연구실을 찾고 있어요', 'out_of_scope'),
                             ('컴퓨터가 좋아요', 'too_broad'), ('ㅇㅇ', 'nonsense'), ('로봇은 싫어요', 'need_likes')]:
            result = engine.search(text)
            self.assertEqual((result['intent'], result['labs']), (intent, []), text)
            self.assertTrue(result['message'])

    def test_without_worker_dictionary_mode_pushes_disliked_labs_back(self):
        engine = QueryEngine(self.catalog, EmbedBroker(TOKEN))     # 워커 없음 → 후퇴
        result = engine.search('로봇은 싫은데 컴퓨터 구조는 좋아요')
        self.assertEqual(result['mode'], 'dictionary')
        top = [c['id'] for c in result['labs'][:5]]
        robotics = {lid for lid in self.catalog.profiles if 'robotics' in engine.primary[lid]}
        arch = {lid for lid in self.catalog.profiles if 'computer_architecture' in engine.primary[lid]}
        self.assertTrue(set(top) & arch)
        self.assertFalse((set(top) & robotics) - arch)

    def test_missing_worker_starts_once_and_preserves_interpreted_query(self):
        class Launcher:
            calls = 0
            def ensure_started(self):
                self.calls += 1
                return True

        launcher = Launcher()
        engine = QueryEngine(self.catalog, EmbedBroker(TOKEN), launcher=launcher)
        result = engine.search('로봇은 싫은데 컴퓨터 구조는 좋아요')
        self.assertEqual(result['mode'], 'starting')
        self.assertEqual(result['interpretation'], {'likes': ['컴퓨터 구조'], 'dislikes': ['로봇']})
        self.assertTrue(result['labs'])
        self.assertEqual(launcher.calls, 1)

    def test_embedding_mode_uses_worker_similarity_and_builds_cards(self):
        broker = EmbedBroker(TOKEN)
        target = self.lab_ids[7]
        worker = FakeWorker(broker, self.lab_ids, {'뭔가 낯선 표현': {target: 0.5}})
        worker.start()
        self.addCleanup(lambda: setattr(worker, 'stop', True))
        time.sleep(0.3)
        result = QueryEngine(self.catalog, broker).search('뭔가 낯선 표현')
        self.assertEqual(result['mode'], 'embedding')
        self.assertEqual(result['labs'][0]['id'], target)
        card = result['labs'][0]
        self.assertEqual(card['connection'], 'semantic')
        self.assertTrue(card['evidence'] and card['evidence'][0]['text'])
        self.assertIn('원문에서 확인', card['reason'])
        self.assertTrue(result['uncertain'])           # 사전에도 안 맞고 유사도도 낮은 질의는 확신도 낮음
        again = QueryEngine(self.catalog, broker).search('뭔가 낯선 표현')
        self.assertEqual(again['labs'][0]['id'], target)
        self.assertEqual(sum(1 for seen in worker.seen if '뭔가 낯선 표현' in seen), 1)   # 두 번째는 캐시

    def test_slow_worker_falls_back_to_dictionary(self):
        broker = EmbedBroker(TOKEN)
        broker.last_poll = time.time()                  # 워커가 살아 있다고 표시했지만 아무도 응답하지 않음
        result = QueryEngine(self.catalog, broker, timeout=0.3).search('강화학습에 관심 있어요')
        self.assertEqual(result['mode'], 'dictionary')
        self.assertTrue(result['labs'])

    @unittest.skipUnless((QU / 'V2' / 'sims_v2.json').exists() and (QU / 'V2_results.json').exists(), 'experiment outputs are needed')
    def test_engine_reproduces_experiment_rankings_from_recorded_similarities(self):
        sims = json.load(open(QU / 'V2' / 'sims_v2.json', encoding='utf-8'))
        lab_ids = sims['lab_ids']
        table = {p: {'sims': dict(zip(lab_ids, row)), 'best': {lid: -1 for lid in lab_ids}} for p, row in sims['sims']['0'].items()}

        class Recorded:
            def request(self, phrases, timeout):
                return {p: table[p] for p in phrases} if all(p in table for p in phrases) else None

        engine = QueryEngine(self.catalog, Recorded())
        recorded = json.load(open(QU / 'V2_results.json', encoding='utf-8'))
        queries = {**{q['id']: q for q in json.load(open(QU / 'queries.json', encoding='utf-8'))},
                   **{q['id']: q for q in json.load(open(QU / 'queries_test.json', encoding='utf-8'))}}
        # The interpreter now strips "(정말) 재밌었어요" endings, so these phrases have no recorded similarity;
        # q22 'VR은 질렸고', t30 'VR이나': an abbreviation before a particle now normalizes (VR → 가상현실).
        reparsed = {'t55', 't58', 'q22', 't30'}
        checked = 0
        for split in ('dev', 'test'):
            for qid, row in recorded[split]['P'].items():
                if row['intent'] != 'search' or not row.get('rank') or qid in reparsed:
                    continue
                got = engine.search(queries[qid]['text'])
                self.assertEqual(got['mode'], 'embedding', qid)
                self.assertEqual([c['id'] for c in got['labs']], row['rank'][:10], qid)
                self.assertEqual(got['uncertain'], bool(row['routed']), qid)
                checked += 1
        self.assertGreater(checked, 90)


@unittest.skipUnless((DATA / 'courses.jsonl').exists(), 'MVP course data is needed')
class WorkerHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        catalog = ProfileCatalog(DATA)
        self.broker = EmbedBroker(TOKEN)
        self.server = make_server('127.0.0.1', 0, catalog, Store(Path(self.tmp.name) / 'app.sqlite'), engine=QueryEngine(catalog, self.broker), broker=self.broker)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.lab_ids = sorted(catalog.profiles)

    def call(self, path, data=None, token=TOKEN, forwarded=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        if forwarded:
            headers['X-Forwarded-For'] = forwarded
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = self.client.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        return response.status, json.loads(response.read())

    def test_worker_endpoints_require_the_token(self):
        self.assertEqual(self.call('/api/worker/poll?wait=0', token=None)[0], 401)
        self.assertEqual(self.call('/api/worker/poll?wait=0', token='wrong')[0], 401)
        self.assertEqual(self.call('/api/worker/answer', {'job_id': 1, 'lab_ids': [], 'sims': {}, 'best': {}}, token=None)[0], 401)
        self.assertEqual(self.call('/api/worker/poll?wait=0'), (200, {'job': None}))

    def test_worker_round_trip_through_search_api(self):
        self.assertEqual(self.call('/api/engine', token=None), (200, {'embedding': False}))
        stop = threading.Event()

        def work():            # HTTP로 poll/answer 하는 워커
            while not stop.is_set():
                try:
                    _, body = self.call('/api/worker/poll?wait=1')
                    job = body['job']
                    if job:
                        sims = {p: [0.9 if i == 3 else 0.3 for i in range(len(self.lab_ids))] for p in job['phrases']}
                        best = {p: [0] * len(self.lab_ids) for p in job['phrases']}
                        self.call('/api/worker/answer', {'job_id': job['id'], 'lab_ids': self.lab_ids, 'sims': sims, 'best': best})
                except Exception:       # 테스트가 끝나 서버가 내려갔을 때
                    return
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        self.addCleanup(stop.set)
        time.sleep(1.5)
        self.assertEqual(self.call('/api/engine', token=None), (200, {'embedding': True}))
        status, found = self.call('/api/search', {'interests': '표현이 낯선 새로운 관심', 'goal': 'explore'}, token=None)
        self.assertEqual(status, 200)
        self.assertEqual((found['mode'], found['intent']), ('embedding', 'search'))
        self.assertEqual(found['labs'][0]['id'], self.lab_ids[3])
        self.assertNotIn('reasons', found)

    def test_search_without_worker_still_answers_and_non_search_intent_is_explained(self):
        status, found = self.call('/api/search', {'interests': '로봇은 싫은데 컴퓨터 구조는 좋아요', 'goal': 'explore'}, token=None)
        self.assertEqual((status, found['mode']), (200, 'dictionary'))
        status, found = self.call('/api/search', {'interests': '대학원을 가야 할지 모르겠어요', 'goal': 'explore'}, token=None)
        self.assertEqual((found['intent'], found['labs']), ('career', []))

    def test_search_rate_limit_is_per_forwarded_client(self):
        for _ in range(20):
            self.assertEqual(self.call('/api/search', {'interests': '강화학습', 'goal': 'explore'}, token=None, forwarded='203.0.113.5')[0], 200)
        self.assertEqual(self.call('/api/search', {'interests': '강화학습', 'goal': 'explore'}, token=None, forwarded='203.0.113.5')[0], 429)
        self.assertEqual(self.call('/api/search', {'interests': '강화학습', 'goal': 'explore'}, token=None, forwarded='203.0.113.9')[0], 200)


if __name__ == '__main__':
    unittest.main()
