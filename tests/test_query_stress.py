"""Student queries against the parser's golden file (tests/fixtures/query_golden.json) and invariants every answer
must keep: the parse never turns a dislike into a like or leaves one-letter phrases, a refusal carries a message, and
every card the results page draws has the fields curri/static/app.js reads (a course card without matched_topics
once broke the page)."""
import json
import re
import unittest
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine, RagQueryEngine, classify_curated_query
from curri.embed_broker import query_key
from curri.rag.remote import RemoteReranker, RemoteRetriever

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / 'tests' / 'fixtures' / 'query_golden.json').read_text(encoding='utf-8'))['queries']
REFUSALS = {'nonsense', 'career', 'too_broad', 'need_likes', 'need_clarification'}


def squash(text):
    return re.sub(r'\s+', '', text.lower())


def misses(case):
    """What the parse gets wrong against the case's oracle ([] when it matches)."""
    parsed = classify_curated_query(case['text'])
    likes, dislikes = [squash(p) for p in parsed['likes']], [squash(p) for p in parsed['dislikes']]
    out = [] if parsed['intent'] in case['intent'] else [f"intent {parsed['intent']}"]
    out += [f'like {alts[0]}' for alts in case.get('likes', []) if not any(squash(a) in p for a in alts for p in likes)]
    out += [f'dislike {alts[0]}' for alts in case.get('dislikes', []) if not any(squash(a) in p for a in alts for p in dislikes)]
    out += [f'forbidden {t}' for t in case.get('forbid_like', []) if any(squash(t) in p for p in likes)]
    return out


def card_problems(card):
    """The fields labCard / cardOverview / evidenceList read, with their types."""
    out = [k for k in ('id', 'department', 'url', 'reason') if not isinstance(card.get(k), str)]
    if not (isinstance(card.get('professors'), list) and card['professors']):
        out.append('professors')
    topics = card.get('topics')
    if not (isinstance(topics, list) and all(isinstance(t, dict) and 'id' in t and 'label' in t for t in topics)):
        out.append('topics')
        topics = []
    if not isinstance(card.get('matched_topics'), list) or not set(card['matched_topics']) <= {t['id'] for t in topics}:
        out.append('matched_topics')
    if not isinstance(card.get('evidence'), list) or not all(isinstance(e, dict) for e in card['evidence']):
        out.append('evidence')
    return out


class GoldenParseTests(unittest.TestCase):
    def test_golden_cases_parse_as_a_reader_would(self):
        broken = {c['id']: misses(c) for c in GOLDEN if not c.get('known_gap') and misses(c)}
        self.assertEqual(broken, {})

    def test_known_gaps_are_still_gaps(self):
        # A gap that now parses well should lose its known_gap flag so it is guarded from then on.
        fixed = [c['id'] for c in GOLDEN if c.get('known_gap') and not misses(c)]
        self.assertEqual(fixed, [])

    def test_parse_invariants(self):
        for case in GOLDEN:
            with self.subTest(case=case['id']):
                parsed = classify_curated_query(case['text'])
                likes, dislikes = parsed['likes'], parsed['dislikes']
                self.assertFalse([p for p in likes if len(squash(p)) <= 1], 'one-letter liked phrase')
                self.assertFalse(set(map(squash, likes)) & set(map(squash, dislikes)), 'a phrase both liked and disliked')
                if parsed['intent'] in REFUSALS:
                    self.assertTrue(parsed['message'])
                else:
                    self.assertTrue(likes)


class CardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CuratedCatalog(ROOT / 'data' / 'sunwoo')

    def check(self, engine):
        for case in GOLDEN:
            with self.subTest(case=case['id']):
                result = engine.search(case['text'])
                if result['intent'] == 'search':
                    for card in result['labs']:
                        self.assertEqual(card_problems(card), [], card.get('id'))
                else:
                    self.assertTrue(result['message'])

    def test_dictionary_cards_keep_the_page_contract(self):
        self.check(CuratedQueryEngine(self.catalog))

    def test_search_engine_cards_keep_the_page_contract(self):
        labs = list(self.catalog.profiles)
        chunks = {f'c-{lid}': {'id': f'c-{lid}', 'owner': lid, 'kind': 'intro', 'meta': {},
                               'text': 'a chunk about the research of this lab, long enough to quote'} for lid in labs}

        class Broker:  # every lab scores by a stable hash, so course-only labs and search labs both appear
            def available(self):
                return True

            def cached(self, phrases):
                return False

            def understand(self, phrases, query, timeout=6.0, remote=True):
                if query['op'] == 'rerank':
                    answer = {'scores': [0.5] * len(query['documents'])}
                else:
                    answer = {'labs': {p: {lid: [(hash((p, lid)) % 100) / 100, [[f'c-{lid}', 0.5]]] for lid in labs}
                                       for p in query['phrases']}}
                return {query_key(query): answer}
        broker = Broker()
        self.check(RagQueryEngine(self.catalog, broker, RemoteRetriever(broker, chunks), reranker=RemoteReranker(broker)))


if __name__ == '__main__':
    unittest.main()
