import unittest
import json
import tempfile
from pathlib import Path

from curri.curated_catalog import CuratedCatalog, course_base, informative_lab_name, search_terms
from curri.curated_query_engine import GATE_MARGIN, CuratedQueryEngine, classify_curated_query
from curri.embed_broker import query_key


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
        self.assertEqual(top['evidence'][0]['kind'], '과목 설명')
        self.assertTrue(top['evidence'][0]['title'].startswith('선형대수학 (MATH400)'))
        teachers = {p['lab_id'] for p in self.catalog.course_map['CSED311']['professors']}
        result = engine.search('컴퓨터구조 수업이 정말 재밌었어요')
        self.assertTrue(teachers & {c['id'] for c in result['labs'][:5]})
        self.assertNotIn('공식 선수과목', ' '.join(c['reason'] for c in result['labs']))

    def test_topic_that_shares_a_course_title_is_not_course_led(self):
        result = CuratedQueryEngine(self.catalog).search('컴퓨터 구조와 시스템 보안이 좋아요')
        self.assertEqual(result['labs'][0]['connection'], 'direct')
        self.assertEqual(course_base('유기화학II'), '유기화학')
        self.assertEqual(course_base('일반물리(H): 역학과 파동'), '일반물리')

    def test_course_search_regressions_and_aliases(self):
        engine = CuratedQueryEngine(self.catalog)
        def top(query):
            return [c['professors'][0] for c in engine.search(query)['labs'][:5]]
        self.assertNotIn('이상민', top('컴퓨터구조 수업이 정말 재밌었어요'))
        self.assertNotIn('김현우', top('일반물리 수업이 재밌었어요'))
        self.assertEqual(top('선형대수 재밌었어요')[0], '최영주')
        self.assertIn('김현우', top('유기화학 수업이 좋았어요'))
        for alias, code in [('선대', 'MATH400'), ('일물', 'PHYS101'), ('컴구', 'CSED311'),
                            ('운체', 'CSED312'), ('자료구조', 'CSED233')]:
            with self.subTest(alias=alias):
                self.assertIn(code, [c['code'] for c, _ in self.catalog.courses_named([alias], False)])
                self.assertIn(code, [c['code'] for c in engine.search(alias + ' 재밌었어요').get('courses', [])])
        for word in ['선', '일', '컴구름', '선대칭', '운체계']:
            self.assertFalse(self.catalog.courses_named([word], False), word)

    def test_curated_phrase_splitting_reaches_broker(self):
        class Broker:
            def request(self, phrases, timeout):
                self.phrases = phrases
                return {p: {'sims': {}, 'best': {}} for p in phrases}
        from curri.curated_query_engine import classify_curated_query
        cases = [('알고리즘 수업 듣고 이론에 빠졌어요', ['알고리즘', '이론']),
                 ('로봇 팔을 강화학습으로 제어하고 싶어요', ['로봇 팔', '강화학습']),
                 ('인공지능을 활용한 신약 개발', ['인공지능을 활용한 신약 개발'])]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(classify_curated_query(query)['likes'], expected)
                broker = Broker()
                result = CuratedQueryEngine(self.catalog, broker).search(query)
                self.assertEqual(result['mode'], 'embedding')
                self.assertTrue(all(p in broker.phrases for p in expected))

    def test_evidence_shows_one_sentence_with_query_terms(self):
        card = next(c for c in self.catalog.search('자율주행') if c['professors'][0] == '곽수하')
        paper = next(e for e in card['evidence'] if e['section'] == 'representative_paper')
        self.assertLessEqual(len(paper['snippet']), 241)
        self.assertNotIn(paper['title'], paper['snippet'])
        self.assertTrue(paper['marks'] and all(m in paper['snippet'] for m in paper['marks']))
        area = next(e for e in self.catalog.detail(card['id'])['evidence'] if e['section'] == 'research_area')
        self.assertEqual((area['kind'], area['snippet']), ('연구 분야', ''))

    def test_course_reason_names_the_shared_content(self):
        lid = next(l for l, p in self.catalog.profiles.items() if p['professors'][0] == '곽수하')
        courses = self.catalog.detail(lid)['courses']
        linked = [c for c in courses if c['link']]
        self.assertTrue(linked)
        for c in linked:
            self.assertTrue(all(w in c['reason'] for w in c['link']['shared'][:3]))
        self.assertTrue(all(c['reason'] for c in courses))

    def test_question_words_do_not_count_as_topics(self):
        terms = search_terms('잠이 인체에 영향을 미치는 것을 연구하고 싶다')
        self.assertEqual(set(terms), {'잠', '인체'})
        self.assertEqual(terms['잠'], ['sleep', '수면'])

    def test_short_korean_word_is_not_formed_across_two_words(self):
        topic = {'label_ko': '식물인 체관 수송', 'quote': '체관을 연구한다'}
        self.assertFalse(self.catalog._within_a_word('인체', topic))
        self.assertTrue(self.catalog._within_a_word('회로', {'label_ko': '집적회로', 'quote': ''}))

    def test_namesake_paper_is_kept_in_place_but_never_shown_or_searched(self):
        lab, topic = next((lid, t) for lid, p in self.catalog.profiles.items() for t in p['topics'] if t.get('suspect'))
        self.assertIn(topic, self.catalog.profiles[lab]['topics'])  # stored embeddings refer to topics by position
        self.assertNotIn(topic['label_ko'], [e['label'] for e in self.catalog.detail(lab)['evidence']])
        words = ' '.join(topic['label_ko'].split()[:6])
        self.assertNotIn(lab, [c['id'] for c in self.catalog.search(words) if topic['concept'] in c['matched_topics']])

    def test_labs_ranked_only_by_a_namesake_paper_or_ordinary_words_are_dropped(self):
        lab, index = next((lid, i) for lid, p in self.catalog.profiles.items() for i, t in enumerate(p['topics']) if t.get('suspect'))
        others = [l for l in self.catalog.profiles if l != lab]
        sims = {lid: 1.0 - n / 400 for n, lid in enumerate([lab] + others)}
        phrase = '인체에 미치는 작용'
        best = {lid: 0 for lid in sims} | {lab: index}

        class Broker:
            def request(self, phrases, timeout, remote=True):
                return {p: {'sims': sims, 'best': best} for p in phrases}
        ordinary = others[-1]
        engine = CuratedQueryEngine(self.catalog, Broker())
        original = self.catalog.search
        self.catalog.search = lambda text: [{**self.catalog.card(ordinary), 'score': 9.0, 'strong': False, 'evidence': [], 'matched_topics': []}]
        try:
            found = [c['id'] for c in engine.search(phrase)['labs']]
        finally:
            self.catalog.search = original
        self.assertNotIn(lab, found)
        self.assertNotIn(ordinary, found)

    def analysing_broker(self, analysis, target=None):
        labs = list(self.catalog.profiles)
        sims = {lid: 0.5 - n / 1000 for n, lid in enumerate(labs)}

        class Broker:
            seen = None

            def understand(self, phrases, query, timeout, remote=True):
                Broker.seen = query
                return {**{p: {'sims': sims, 'best': {lid: -1 for lid in sims}} for p in phrases}, query_key(query): analysis}
        return Broker()

    def test_worker_can_refuse_a_query_the_rules_let_through(self):
        for label, intent in (('off_topic', 'nonsense'), ('procedure', 'career'), ('too_vague', 'too_broad'), ('only_dislike', 'need_likes')):
            found = CuratedQueryEngine(self.catalog, self.analysing_broker({'intent': label, 'margin': 0.2})).search('저녁에 치킨 시킬까')
            self.assertEqual((found['intent'], found['labs']), (intent, []))

    def test_chunk_and_reranker_lists_join_the_fusion(self):
        labs = list(self.catalog.profiles)
        target = labs[-1]
        favoured = {target: 1.0, **{lid: 0.0 for lid in labs[:-1]}}
        broker = self.analysing_broker({'intent': 'search', 'margin': -0.2, 'english': '', 'chunk': favoured, 'rerank': favoured, 'penalties': []})
        self.assertIn(target, [c['id'] for c in CuratedQueryEngine(self.catalog, broker).search('아주 낯선 표현을 연구하고 싶어요')['labs']])
        self.assertEqual(broker.seen['gate'], GATE_MARGIN)

    def test_a_stated_dislike_skips_the_refusal_check_and_stays_out_of_the_search_text(self):
        labs = list(self.catalog.profiles)
        broker = self.analysing_broker({'english': '', 'chunk': {lid: 0.0 for lid in labs}, 'rerank': {}, 'penalties': [{lid: 0.0 for lid in labs}]})
        CuratedQueryEngine(self.catalog, broker).search('로봇은 싫고 반도체가 좋아요')
        self.assertIsNone(broker.seen['gate'])
        self.assertEqual((broker.seen['text'], broker.seen['dislikes']), ('반도체', ['로봇']))

    def test_an_interest_with_an_unparsed_avoidance_skips_the_refusal_check(self):
        labs = list(self.catalog.profiles)
        broker = self.analysing_broker({'english': '', 'chunk': {lid: 0.0 for lid in labs}, 'rerank': {}, 'penalties': []})
        CuratedQueryEngine(self.catalog, broker).search('효소 연구는 하고 싶은데 동물 실험은 절대 못 하겠어요')
        self.assertIsNone(broker.seen['gate'])

    def test_translation_reaches_the_dictionary_search(self):
        labs = list(self.catalog.profiles)
        broker = self.analysing_broker({'intent': 'search', 'margin': -0.2, 'english': 'graphene', 'chunk': {lid: 0.0 for lid in labs}, 'rerank': {}, 'penalties': []})
        engine = CuratedQueryEngine(self.catalog, broker)
        seen, original = [], self.catalog.search
        self.catalog.search = lambda text: seen.append(text) or []
        try:
            engine.search('아주 낯선 표현을 연구하고 싶어요')
        finally:
            self.catalog.search = original
        self.assertIn('아주 낯선 표현을 연구하고 싶어요 graphene', seen)

    def test_a_worker_without_analysis_keeps_the_phrase_search(self):
        found = CuratedQueryEngine(self.catalog, self.analysing_broker(None)).search('강화학습에 관심 있어요')
        self.assertEqual((found['intent'], found['mode']), ('search', 'embedding'))

    def test_long_phrases_are_not_quoted_back_in_the_reason(self):
        lab = next(iter(self.catalog.profiles))
        engine = CuratedQueryEngine(self.catalog, None)
        self.assertIn('‘반도체’와', engine.semantic_card(lab, 1.0, ('반도체', -1))['reason'])
        self.assertIn('‘로봇’과', engine.semantic_card(lab, 1.0, ('로봇', -1))['reason'])
        long_phrase = '세포 배양 실험 코딩은 최대한 안 했으면'
        reason = engine.semantic_card(lab, 1.0, (long_phrase, -1))['reason']
        self.assertTrue(reason.startswith('입력한 관심과 의미가'), reason)

    def test_request_wording_is_removed_from_likes(self):
        self.assertEqual(classify_curated_query('방사선 연구하는 곳 있어?')['likes'], ['방사선'])

    def test_avoidance_alone_asks_for_an_interest(self):
        self.assertEqual(classify_curated_query('납땜은 피하고 싶어요')['intent'], 'need_likes')

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
