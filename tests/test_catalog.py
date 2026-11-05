import json
import tempfile
import unittest
from pathlib import Path
from curri.catalog import Catalog, excerpt


def fixture(path):
    labs = [
        {'record_id': 'bio', 'professor_name': '생명 교수', 'department': 'Life', 'lab_url': 'https://bio.example', 'data_status': 'collected', 'quality_flags': [], 'sections': {'research_intro': {'text': 'We study biology and genomics using machine learning and artificial intelligence.', 'source_urls': ['https://bio.example/research']}}},
        {'record_id': 'ai', 'professor_name': 'AI 교수', 'department': 'CS', 'lab_url': 'https://ai.example', 'data_status': 'collected', 'quality_flags': [], 'sections': {'research_intro': {'text': 'Machine learning algorithms and optimization.', 'source_urls': ['https://ai.example/research']}}},
        {'record_id': 'duplicate', 'professor_name': '공동 교수', 'department': 'Life', 'lab_url': 'http://bio.example/', 'data_status': 'collected', 'quality_flags': [], 'sections': {'research_intro': {'text': 'Biology and machine learning.', 'source_urls': ['https://bio.example/research']}}},
        {'record_id': 'bad', 'professor_name': '실패', 'lab_url': 'https://bad.example', 'data_status': 'excluded', 'sections': {}},
    ]
    courses = [
        {'record_id': 'ml', 'course_code': 'CS101', 'course_name_kr': '기계학습', 'course_name_en': 'Machine Learning', 'description': 'Machine learning and artificial intelligence algorithms.', 'objectives': '', 'course_plan': '', 'prerequisites_text': '', 'quality_flags': []},
        {'record_id': 'life', 'course_code': 'LIFE101', 'course_name_kr': '생명과학', 'course_name_en': 'Biology', 'description': 'Biology and genomics.', 'objectives': '', 'course_plan': '', 'prerequisites_text': '', 'quality_flags': []},
        {'record_id': 'unrelated', 'course_code': 'LAW101', 'course_name_kr': '법학', 'course_name_en': 'Law', 'description': 'Constitutional law.', 'quality_flags': []},
    ]
    for name, rows in [('labs', labs), ('courses', courses)]:
        (path / f'{name}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        fixture(Path(self.tmp.name))
        self.catalog = Catalog(Path(self.tmp.name))

    def test_interests_not_course_history_find_cross_domain_evidence(self):
        results = self.catalog.search('생명과학과 AI에 관심이 있어요')
        bio = next(r for r in results if r['id'] == 'bio')
        self.assertEqual(set(bio['matched_topics']), {'biology', 'ai'})
        self.assertTrue(all(e['text'] and e['urls'] for e in bio['evidence']))
        self.assertEqual(len(results), 2)
        self.assertEqual(len(bio['professors']), 2)
        self.assertEqual(self.catalog.resolve('duplicate'), 'bio')

    def test_unknown_interest_does_not_get_arbitrary_recommendations(self):
        self.assertEqual(self.catalog.search('중세 프랑스 법률사'), [])
        self.assertEqual(self.catalog.search(''), [])

    def test_related_courses_exclude_unrelated_and_zero_history_is_allowed(self):
        detail = self.catalog.detail('bio')
        self.assertEqual({c['id'] for c in detail['courses']}, {'ml', 'life'})
        guide = self.catalog.guide('bio', [])
        self.assertEqual(guide['selected_courses'], [])
        self.assertTrue(guide['start_now'])
        self.assertTrue(guide['prepare_next'])
        self.assertTrue(all(x['evidence'] for x in guide['start_now'] + guide['prepare_next']))

    def test_selected_courses_change_preparation_without_claiming_biology_expertise(self):
        guide = self.catalog.guide('bio', ['ml'])
        self.assertEqual([c['id'] for c in guide['selected_courses']], ['ml'])
        self.assertIn('life', {c['id'] for c in guide['recommended_courses']})
        self.assertNotIn('ml', {c['id'] for c in guide['recommended_courses']})
        self.assertNotEqual(guide, self.catalog.guide('bio', []))

    def test_forged_or_unrelated_course_and_excluded_lab_are_rejected(self):
        for ids in [['fake'], ['unrelated']]:
            with self.assertRaises(ValueError):
                self.catalog.guide('bio', ids)
        with self.assertRaises(KeyError):
            self.catalog.detail('bad')

    def test_publication_only_side_topic_does_not_override_research_intro(self):
        path = Path(self.tmp.name) / 'labs.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[1]['sections']['publications'] = {'text': 'Biological Institute conference 2005.', 'source_urls': ['https://ai.example/papers']}
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        catalog = Catalog(Path(self.tmp.name))
        self.assertNotIn('ai', [r['id'] for r in catalog.search('생명과학')])

    def test_excerpt_points_to_the_actual_word_not_letters_inside_another_word(self):
        text = 'AAAI conference. ' + 'background ' * 80 + 'AI research for medicine.'
        self.assertIn('AI research', excerpt(text, ['ai']))

    def test_generic_computing_environment_and_contact_degree_do_not_become_research(self):
        path = Path(self.tmp.name) / 'labs.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['sections']['research_intro']['text'] = '블록체인 다중 경로 환경에서 결제 환경을 연구합니다.'
        rows[1]['sections']['research_intro']['text'] = 'Research\nAddress:\nPOSTECH Institute of Artificial Intelligence\nTEL:\n1234'
        rows[2]['lab_url'] = 'https://student.example'
        rows[2]['sections']['research_intro']['text'] = 'Researchers and Students 1 페이지\nEducation\nM.S. student at Graduate School of Semiconductor Technology'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        catalog = Catalog(Path(self.tmp.name))
        self.assertEqual(catalog.search('환경'), [])
        self.assertEqual(catalog.search('AI'), [])
        self.assertEqual(catalog.search('반도체'), [])
