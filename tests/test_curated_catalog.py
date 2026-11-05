import unittest
import json
import tempfile
from pathlib import Path

from curri.curated_catalog import CuratedCatalog, course_base, informative_lab_name
from curri.curated_query_engine import CuratedQueryEngine


DATA = Path(__file__).resolve().parents[1] / 'data' / 'sunwoo'


class CuratedCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = CuratedCatalog(DATA)

    def test_query_parsing_keeps_clauses_apart_and_drops_noise(self):
        from curri.query_engine import interpret, normalize
        cases = {'배터리 전해질 소재가 궁금한데 계산 시뮬레이션은 싫어요': (['배터리 전해질 소재'], ['계산 시뮬레이션']),
                 '로봇은 좋은데 하드웨어는 싫어요': (['로봇'], ['하드웨어']),
                 '생물은 싫지만 뇌과학은 궁금해요': (['뇌과학'], ['생물']),
                 'LLM 언어모델': (['언어모델'], []), '반도체 공정 ㅋㅋ': (['반도체 공정'], [])}
        for text, (likes, dislikes) in cases.items():
            self.assertEqual(interpret(normalize(text)), {'likes': likes, 'dislikes': dislikes}, text)
        self.assertEqual(normalize('ㅋㅋㅋㅋ'), '')

    def test_dictionary_search_finds_english_material_and_prefers_topic_words(self):
        def top(query, n=5):
            return [p for lab in self.catalog.search(query)[:n] for p in lab['professors']]
        self.assertTrue({'강석형', '곽수하', '김슬배', '배경민'} & set(top('자율주행 자동차 인지', 3)))  # English "autonomous driving"
        self.assertTrue(self.catalog.search('자연어처리'))
        self.assertEqual(self.catalog.search('언어 모델')[0]['id'], self.catalog.search('언어모델')[0]['id'])  # spacing
        self.assertTrue(all(lab['department'].startswith('산업경영') for lab in self.catalog.search('금융 공학')[:3]))  # 공학 alone is too common to rank

    def test_former_lab_ids_resolve_to_the_same_professor(self):
        aliases = json.loads((DATA / 'legacy_lab_aliases.json').read_text(encoding='utf-8'))['aliases']
        self.assertGreater(len(aliases), 50)
        for old, new in aliases.items():
            self.assertEqual(self.catalog.resolve(old), new)
        with self.assertRaises(KeyError):
            self.catalog.resolve(next(iter(json.loads((DATA / 'legacy_lab_aliases.json').read_text(encoding='utf-8'))['unmapped'])))

    def test_only_curated_recommendable_entities_are_loaded(self):
        self.assertEqual(len(self.catalog.profiles), 307)
        self.assertEqual(len(self.catalog.courses), 1151)
        source_ids = {row['id'] for row in map(json.loads, (DATA / 'labs.jsonl').read_text().splitlines())
                      if row['recommendable']}
        self.assertEqual(set(self.catalog.profiles), source_ids)
        self.assertTrue(all(isinstance(self.catalog.card(lid)['professors'][0], str)
                            for lid in self.catalog.profiles))

    def test_query_interprets_dislikes_and_returns_source_backed_labs(self):
        result = CuratedQueryEngine(self.catalog).search('로봇은 싫은데 컴퓨터 구조와 시스템 보안은 좋아요')
        self.assertEqual(result['interpretation']['dislikes'], ['로봇'])
        self.assertEqual(result['interpretation']['likes'], ['컴퓨터 구조', '시스템 보안'])
        self.assertTrue(result['labs'])
        for card in result['labs']:
            self.assertIn(card['id'], self.catalog.profiles)
            self.assertTrue(card['evidence'])

    def test_nonsearch_and_ambiguous_negation_never_reach_worker(self):
        class Broker:
            def request(self, *_):
                raise AssertionError('nonsearch query reached embedding worker')

        engine = CuratedQueryEngine(self.catalog, Broker())
        for query, intent in [
            ('수강신청은 어떻게 하나요', 'career'),
            ('대학원 지원 방법을 알려줘', 'career'),
            ('교수님께 메일을 어떻게 쓰나요', 'career'),
            ('asdf', 'nonsense'), ('ㅋㅋㅋㅋ', 'nonsense'),
            ('인공지능', 'too_broad'),
            ('로봇이 재미없지만 의료 영상은 좋아요', 'need_clarification'),
        ]:
            with self.subTest(query=query):
                result = engine.search(query)
                self.assertEqual(result['intent'], intent)
                self.assertEqual(result['labs'], [])
                self.assertTrue(result['message'])

    def test_explicit_negative_is_extracted_without_blocking_related_research(self):
        engine = CuratedQueryEngine(self.catalog)
        result = engine.search('로봇을 좋아하지 않지만 뇌 신호 분석은 좋아요')
        self.assertEqual(result['intent'], 'search')
        self.assertIn('로봇', result['interpretation']['dislikes'])
        self.assertTrue(result['labs'])
        result = engine.search('대학원에서 로봇을 연구하고 싶어요')
        self.assertEqual(result['intent'], 'search')

    def test_explicit_topic_conflict_is_removed_after_rank_fusion(self):
        class Broker:
            def request(self, phrases, *_):
                ids = list(self_ids)
                return {phrase: {'sims': {lid: float(i) for i, lid in enumerate(ids)},
                                 'best': {lid: 0 for lid in ids}}
                        for phrase in phrases}

        self_ids = self.catalog.profiles
        engine = CuratedQueryEngine(self.catalog, Broker())
        result = engine.search('로봇은 싫고 배터리가 좋아요')
        self.assertEqual(result['mode'], 'embedding')
        self.assertTrue(result['labs'])
        self.assertTrue(all(not engine.conflicts_with_dislikes(card['id'], ['로봇'])
                            for card in result['labs']))

    def test_course_candidates_are_from_curated_catalog(self):
        if not self.catalog.course_similarity:
            self.skipTest('precomputed BGE-M3 mapping not available yet')
        lid = next(iter(self.catalog.course_similarity))
        detail = self.catalog.detail(lid)
        self.assertTrue(detail['courses'])
        self.assertTrue(all(c['id'] in self.catalog.course_map for c in detail['courses']))
        self.assertIn('공식 선수과목', detail['notice'])

    def test_lab_card_uses_topic_labels_instead_of_cropped_crawl_text(self):
        profile = next(p for p in self.catalog.profiles.values() if p['professors'][0] == '김기훈')
        card = self.catalog.card(profile['lab_id'])
        self.assertTrue(card['summary'].startswith('연구 분야: '))
        self.assertNotIn('Research Overview', card['summary'])
        self.assertNotIn('we con', card['summary'])

    def card_of(self, professor):
        lid = next(lid for lid, p in self.catalog.profiles.items() if p['professors'][0] == professor)
        return self.catalog.card(lid)

    def test_lab_name_shown_only_when_it_adds_to_professor_name(self):
        card = self.card_of('조문호')
        self.assertEqual(card['lab_name'], '조문호 교수 연구실')  # source value is kept
        self.assertEqual(card['lab_subtitle'], '')
        self.assertEqual(self.card_of('이정수')['lab_subtitle'], '나노 소자 및 공정 연구실')
        # Professors listed only in English keep that name instead of falling back to the lab name.
        self.assertEqual(self.card_of('Seung Park')['lab_subtitle'], '생체막 다이나믹스 연구실')
        self.assertEqual(self.card_of('Sw Chung')['lab_subtitle'], '차세대 메모리 반도체 소자/공정 연구실 (IMPD)')
        hidden = [c for c in map(self.catalog.card, self.catalog.profiles) if not c['lab_subtitle']]
        self.assertTrue(all(c['professors'][0] in c['lab_name'] for c in hidden))

    def test_class_queries_lead_to_instructor_and_similar_labs(self):
        engine = CuratedQueryEngine(self.catalog)
        result = engine.search('선형대수 재밌었어요')
        self.assertEqual(result['interpretation']['likes'], ['선형대수'])
        self.assertEqual(result['courses'][0]['code'], 'MATH400')  # the exact title before longer ones
        top = result['labs'][0]
        self.assertEqual(top['connection'], 'course')
        self.assertIn('MATH400', top['reason'])
        self.assertTrue(top['evidence'][0]['text'].startswith('선형대수학 과목 설명'))
        teachers = {p['lab_id'] for p in self.catalog.course_map['CSED311']['professors']}
        result = engine.search('컴퓨터구조 수업이 정말 재밌었어요')
        self.assertTrue(teachers & {c['id'] for c in result['labs'][:5]})
        self.assertNotIn('공식 선수과목', ' '.join(c['reason'] for c in result['labs']))

    def test_topic_that_shares_a_course_title_is_not_course_led(self):
        result = CuratedQueryEngine(self.catalog).search('컴퓨터 구조와 시스템 보안이 좋아요')
        self.assertEqual(result['labs'][0]['connection'], 'direct')
        self.assertEqual(course_base('유기화학II'), '유기화학')
        self.assertEqual(course_base('일반물리(H): 역학과 파동'), '일반물리')

    def test_informative_lab_name_rules(self):
        self.assertEqual(informative_lab_name('홍길동 교수 연구실', ['홍길동']), '')
        self.assertEqual(informative_lab_name('홍길동', ['홍길동']), '')
        self.assertEqual(informative_lab_name('Hong Lab', ['Hong']), '')
        self.assertEqual(informative_lab_name('', ['홍길동']), '')
        self.assertEqual(informative_lab_name('홍길동 교수 연구실 (HONG Lab)', ['홍길동']), '홍길동 교수 연구실 (HONG Lab)')
        self.assertEqual(informative_lab_name('기계학습 연구실 (ML Lab)', ['홍길동']), '기계학습 연구실 (ML Lab)')

    def test_overview_lists_lab_areas_and_separates_openalex_topics(self):
        card = self.card_of('조문호')
        overview = card['overview']
        self.assertEqual(overview['source'], 'lab_material')
        self.assertEqual(overview['title'], '연구 분야')
        self.assertEqual(overview['items'], ['새로운 이차원 물질의 에피탁시 합성 (반도체, 반금속, 초전도체 등)',
                                             '지능형 이차원 반도체 전자 소자 및 광반도체 소자 물리',
                                             '이차원 반데르발스 양자 소자 물리'])
        self.assertEqual(overview['classification'], ['2D Materials and Applications'])
        self.assertFalse(card['summary'].endswith(' 외'))
        # The homepage-intro topic is labelled as what it is, not with the lab name again.
        intro = [t for t in card['topics'] if t['section'] == 'research_intro']
        self.assertEqual([t['label'] for t in intro], ['연구실 소개'])
        self.assertNotIn('조문호 교수 연구실', [e['label'] for e in self.catalog.detail(card['id'])['evidence']])

    def test_labs_without_own_areas_say_the_list_is_openalex_classification(self):
        overview = self.card_of('이정수')['overview']
        self.assertEqual(overview['source'], 'openalex_topic')
        self.assertIn('OpenAlex', overview['note'])
        self.assertIn('Semiconductor materials and devices', overview['items'])

    def test_overview_never_presents_openalex_topics_as_lab_areas(self):
        rows = [json.loads(line) for line in (DATA / 'labs.jsonl').read_text().splitlines()]
        areas = {r['id']: {str(a.get('name_ko') or a.get('name_en') or a.get('name') or '').strip().strip('.,;:').strip()
                           for a in r.get('research_areas') or []} for r in rows if r['recommendable']}
        papers = {r['id']: {t.strip('.,;:').strip() for t in r.get('core_topics') or []}
                  for r in map(json.loads, (DATA / 'papers.jsonl').read_text().splitlines())}
        for lid in self.catalog.profiles:
            overview = self.catalog.card(lid)['overview']
            with self.subTest(lab=lid):
                if overview['source'] == 'lab_material':
                    self.assertLessEqual(set(overview['items']), areas[lid])
                    self.assertLessEqual(set(overview['classification']), papers.get(lid, set()))
                elif overview['source'] == 'openalex_topic':
                    self.assertFalse(areas[lid] - {'research overview'})
                    self.assertLessEqual(set(overview['items']), papers.get(lid, set()))

    def test_overview_falls_back_to_profile_labels_without_labs_file(self):
        profile = {'lab_id': 'x', 'professors': ['홍길동'], 'department': '물리학과', 'lab_name': '홍길동 교수 연구실',
                   'lab_url': 'https://example.org', 'status': 'ok', 'summary_ko': '',
                   'topics': [{'concept': 'topic_0', 'label_ko': '양자 소자', 'quote': '양자 소자',
                               'source_urls': [], 'section': 'research_area', 'role': 'domain',
                               'weight': 'primary', 'scope': 'core'}]}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'app_profiles.jsonl').write_text(json.dumps(profile, ensure_ascii=False) + '\n', encoding='utf-8')
            (root / 'courses.jsonl').write_text('', encoding='utf-8')
            card = CuratedCatalog(root).card('x')
        self.assertEqual(card['overview']['items'], ['양자 소자'])
        self.assertEqual(card['lab_subtitle'], '')
