"""The ported vectorRAG search (RagQueryEngine, curri/rag): ranking from the worker's chunk scores, reranker,
R7 rewrites through the AI worker queue, and the fall back to the dictionary search when the worker is off."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import RagQueryEngine
from curri.embed_broker import query_key
from curri.llm_jobs import LLMJobs
from curri.rag import query_llm
from curri.rag.remote import RemoteReranker, RemoteRetriever, Unavailable
from curri.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo'


def chunk(cid, owner, kind='intro', text='', **meta):
    return {'id': cid, 'owner': owner, 'kind': kind, 'text': text or f'{cid} text about the research in some detail', 'meta': meta}


class FakeBroker:
    """EmbedBroker.understand: phrase sims (unused by the RAG path) plus the answer to the query op."""
    def __init__(self, answer, up=True):
        self.answer, self.up, self.calls = answer, up, []

    def available(self):
        return self.up

    def cached(self, phrases):
        return False

    def understand(self, phrases, query, timeout=6.0, remote=True):
        self.calls.append((query, remote))
        if not self.up or not remote:
            return None
        return {**{p: {'sims': {}, 'best': {}} for p in phrases}, query_key(query): self.answer(query)}


class RemoteTests(unittest.TestCase):
    def test_lab_scores_map_chunk_ids_back_to_chunks(self):
        table = {'c1': chunk('c1', 'a'), 'c2': chunk('c2', 'a')}
        broker = FakeBroker(lambda q: {'labs': {p: {'a': [0.9, [['c1', 0.8], ['c2', 0.5], ['gone', 0.1]]]} for p in q['phrases']}})
        found = RemoteRetriever(broker, table).lab_scores(['로봇', '로봇'])
        self.assertEqual(list(found), ['로봇'])
        score, best = found['로봇']['a']
        self.assertEqual(score, 0.9)
        self.assertEqual([c['id'] for _, c in best], ['c1', 'c2'])  # a chunk the server does not know is left out

    def test_no_answer_or_cache_only_is_unavailable(self):
        broker = FakeBroker(lambda q: {})
        with self.assertRaises(Unavailable):
            RemoteRetriever(broker, {}).lab_scores(['로봇'], remote=False)
        with self.assertRaises(Unavailable):
            RemoteReranker(FakeBroker(lambda q: {'scores': [0.1]})).score('q', ['a', 'b'], ['q'])


class QueryRewriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs = LLMJobs(Store(Path(self.tmp.name) / 'app.sqlite'), token='t')
        self.jobs.last_poll = time.time()

    def tearDown(self):
        self.tmp.cleanup()

    def test_waits_for_the_worker_and_keeps_its_answer(self):
        rewrite = query_llm.LlmQuery(self.jobs, wait=5)

        def worker():
            job = self.jobs.poll(wait=5)
            self.assertEqual((job['kind'], job['model'], job['prompt']), ('query', 'haiku', '배터리 오래 가게'))
            self.jobs.answer({'job_id': job['id'], 'ok': True, 'result': {'english': 'battery degradation, cycle life', 'facets': ['x']}})
        thread = threading.Thread(target=worker)
        thread.start()
        self.assertEqual(rewrite('배터리  오래 가게'), {'english': 'battery degradation, cycle life', 'facets': []})
        thread.join()
        self.assertEqual(rewrite('배터리 오래 가게')['english'], 'battery degradation, cycle life')

    def test_a_slow_or_absent_worker_means_no_rewrite(self):
        rewrite = query_llm.LlmQuery(self.jobs, wait=0.3)
        self.assertEqual(rewrite('로봇'), {'english': '', 'facets': []})
        self.assertEqual(self.jobs.get(key=rewrite.key('로봇'))['status'], 'queued')  # answered later, used next time
        self.jobs.last_poll = 0
        self.assertEqual(rewrite('비전'), {'english': '', 'facets': []})
        self.assertIsNone(self.jobs.get(key=rewrite.key('비전')))  # nothing queued while the worker is off
        self.assertEqual(rewrite('로봇', remote=False), {'english': '', 'facets': []})

    def test_daily_limit_and_long_phrases(self):
        from curri import llm_jobs
        old = llm_jobs.DAILY_LIMIT['query']
        llm_jobs.DAILY_LIMIT['query'] = 2
        try:
            rewrite = query_llm.LlmQuery(self.jobs, wait=0)
            rewrite('로봇'), rewrite('비전'), rewrite('로봇')  # the same phrase again is not a new job
            with self.assertRaises(llm_jobs.QuotaExceeded):
                self.jobs.submit('query', 'another', {'x': 1})
            self.assertEqual(rewrite('반도체'), {'english': '', 'facets': []})
            self.assertIsNone(self.jobs.get(key=rewrite.key('반도체')))
            self.jobs.submit('guide', 'g', {'x': 1})  # other kinds keep their own limit
        finally:
            llm_jobs.DAILY_LIMIT['query'] = old
        rewrite('가' * 81)
        self.assertIsNone(self.jobs.get(key=rewrite.key('가' * 81)))

    def test_rewrites_go_before_guides_and_summaries(self):
        self.jobs.submit('summary', 's', {'x': 1})
        self.jobs.submit('guide', 'g', {'x': 1})
        self.jobs.submit('query', 'q', {'x': 1})
        self.assertEqual([self.jobs.poll(0)['kind'] for _ in range(3)], ['query', 'guide', 'summary'])


@unittest.skipUnless((DATA / 'app_profiles.jsonl').exists(), '앱 데이터가 필요합니다')
class RagEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CuratedCatalog(DATA)
        cls.labs = list(cls.catalog.profiles)[:30]

    def engine(self, scores, rerank=None, up=True):
        """scores: {phrase: {lab: score}} (a phrase not listed scores like the first one, a disliked phrase must be
        listed); each lab gets one intro chunk of that score."""
        table = {f'c-{lid}': chunk(f'c-{lid}', lid) for lid in self.labs}

        def answer(q):
            if q['op'] == 'lab_scores' and q.get('gate') is not None and 'chicken' in q.get('raw', ''):
                return {'intent': 'off_topic', 'margin': 0.2}
            if q['op'] == 'lab_scores':
                return {'labs': {p: {lid: [s, [[f'c-{lid}', s]]] for lid, s in scores.get(p, next(iter(scores.values()))).items()} for p in q['phrases']}}
            return {'scores': rerank(q) if rerank else [0.0] * len(q['documents'])}
        broker = FakeBroker(answer, up)
        engine = RagQueryEngine(self.catalog, broker, RemoteRetriever(broker, table), reranker=RemoteReranker(broker) if rerank else None)
        return engine, broker

    def flat(self, best, value=0.5):
        return {lid: (0.95 if lid == best else value) for lid in self.labs}

    def test_ranks_by_the_first_pass_and_quotes_the_chunk(self):
        engine, _ = self.engine({'단백질 구조': self.flat(self.labs[3])})
        result = engine.search('단백질 구조 연구')
        self.assertEqual(result['mode'], 'embedding')
        self.assertEqual(result['labs'][0]['id'], self.labs[3])
        self.assertEqual(result['labs'][0]['evidence'][0]['chunk_id'], f'c-{self.labs[3]}')

    def test_the_reranker_reorders_the_first_candidates(self):
        def rerank(q):
            return [0.9 if q_doc.startswith(self.catalog.profiles[self.labs[7]]['lab_name']) else 0.1 for q_doc in q['documents']]
        scores = self.flat(self.labs[3])
        scores[self.labs[7]] = 0.9
        engine, _ = self.engine({'단백질 구조': scores}, rerank=rerank)
        ids = [c['id'] for c in engine.search('단백질 구조 연구')['labs']]
        self.assertEqual(ids[0], self.labs[7])

    def test_a_disliked_phrase_pushes_its_lab_down(self):
        likes = self.flat(self.labs[3], 0.5)
        likes[self.labs[4]] = 0.94
        engine, _ = self.engine({'단백질 구조': likes, '로봇': self.flat(self.labs[3], 0.1)})
        ids = [c['id'] for c in engine.search('단백질 구조는 좋은데 로봇은 싫어')['labs']]
        self.assertLess(ids.index(self.labs[4]), ids.index(self.labs[3]) if self.labs[3] in ids else 99)

    def test_falls_back_to_the_dictionary_when_the_worker_is_off(self):
        engine, broker = self.engine({}, up=False)
        result = engine.search('단백질 구조 연구')
        self.assertEqual(result['mode'], 'dictionary')
        self.assertTrue(broker.calls)

    def test_the_workers_refusal_check_refuses(self):
        engine, broker = self.engine({'x': self.flat(self.labs[3])})
        result = engine.search('오늘 chicken 시킬까 고민')
        self.assertEqual((result['intent'], result['labs']), ('nonsense', []))
        self.assertEqual(broker.calls[0][0]['gate'], 0.05)
        engine.search('단백질 구조는 좋은데 로봇은 싫어')  # a dislike skips the check, as in CuratedQueryEngine
        self.assertNotIn('gate', broker.calls[-1][0])

    def test_no_new_rewrite_when_the_client_is_over_its_limit(self):
        asked = []
        engine, _ = self.engine({'x': self.flat(self.labs[3])})
        engine.rewriter = lambda phrase, remote=True: asked.append(remote) or {'english': '', 'facets': []}
        engine.search('단백질 구조 연구', rewrite=False)
        engine.search('세포 신호 전달 연구')
        self.assertEqual(asked, [False, True])

    def test_a_refused_query_is_not_rewritten(self):
        asked = []
        engine, _ = self.engine({'x': self.flat(self.labs[3])})
        engine.rewriter = lambda phrase, remote=True: asked.append(phrase) or {'english': 'english terms', 'facets': []}
        self.assertEqual(engine.search('오늘 chicken 시킬까 고민')['intent'], 'nonsense')
        self.assertEqual(asked, [])
        engine.search('단백질 구조 연구')
        self.assertEqual(asked, ['단백질 구조 연구'])

    def test_refusals_never_reach_the_worker(self):
        engine, broker = self.engine({})
        self.assertEqual(engine.search('ㅋㅋㅋ')['intent'], 'nonsense')
        self.assertEqual(broker.calls, [])


if __name__ == '__main__':
    unittest.main()


class BrokerCacheTests(unittest.TestCase):
    def test_cache_is_bounded_by_size_and_the_table_by_rows(self):
        from curri import embed_broker
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'app.sqlite')
            saved = embed_broker.MAX_CACHE_BYTES, embed_broker.MAX_STORED, embed_broker.PRUNE_EVERY
            embed_broker.MAX_CACHE_BYTES, embed_broker.MAX_STORED, embed_broker.PRUNE_EVERY = 200, 3, 1
            try:
                broker = embed_broker.EmbedBroker('t', store=store)
                for n in range(6):
                    broker.answer(n, ['a', 'b'], {f'p{n}': [0.1, 0.2]}, {f'p{n}': [0, 1]})
                self.assertLessEqual(broker.bytes, 200)
                self.assertIn('p5', broker.cache)
                self.assertNotIn('p0', broker.cache)
                with store.db() as db:
                    self.assertLessEqual(db.execute('SELECT COUNT(*) FROM phrase_sims').fetchone()[0], 4)
            finally:
                embed_broker.MAX_CACHE_BYTES, embed_broker.MAX_STORED, embed_broker.PRUNE_EVERY = saved
