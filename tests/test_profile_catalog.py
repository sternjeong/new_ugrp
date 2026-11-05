import json
import re
import unittest
from pathlib import Path
from curri.profile_catalog import ProfileCatalog

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo' / 'legacy' / 'mvp-4dept'


@unittest.skipUnless((DATA / 'courses.jsonl').exists(), 'MVP course data is needed for profile tests')
class ProfileCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ProfileCatalog(DATA)

    def test_every_candidate_has_a_profile_and_quotes_are_verbatim(self):
        norm = lambda s: re.sub(r'\s+', ' ', s).strip().lower()
        for lid, prof in self.catalog.profiles.items():
            members = self.catalog.labs[lid]['members']
            texts = [norm(s.get('text', '')) for m in members for s in m.get('sections', {}).values()]
            for t in prof['topics']:
                if t['section'] == 'reviewer':
                    continue
                self.assertTrue(any(norm(t['quote']) in x for x in texts), (lid, t['quote'][:40]))

    def test_generic_ai_alone_returns_only_ml_centred_labs(self):
        results = self.catalog.search('AI')
        self.assertTrue(results)
        for r in results:
            roles = {t['role'] for t in r['topics'] if t['id'] == 'machine_learning'}
            self.assertIn('domain', roles, r['professors'])
        self.assertLess(len(results), 12)

    def test_specific_phrasing_finds_the_expected_lab_first(self):
        top = [r['professors'][0] for r in self.catalog.search('챗봇이나 자연어 처리')[:6]]
        self.assertTrue(any('이근배' in p for p in top))
        self.assertEqual([r['professors'][0][:3] for r in self.catalog.search('블록체인')[:2]].count('송황준') + [r['professors'][0][:3] for r in self.catalog.search('블록체인')[:2]].count('박찬익'), 2)

    def test_insufficient_labs_never_appear_and_unknown_interest_is_empty(self):
        insufficient = {lid for lid, p in self.catalog.profiles.items() if p['status'] == 'insufficient'}
        self.assertTrue(insufficient)
        for q in ['AI', '반도체', '제어', '로봇', '통신']:
            self.assertFalse(insufficient & {r['id'] for r in self.catalog.search(q)})
        self.assertEqual(self.catalog.search('중세 프랑스 법률사'), [])
        self.assertEqual(self.catalog.search('   '), [])

    def test_shared_homepage_alias_resolves_and_courses_are_bounded(self):
        mads = next(lid for lid, p in self.catalog.profiles.items() if len(p['professors']) == 2 and 'Song' in p['professors'][0])
        member_ids = [m['record_id'] for m in self.catalog.labs[mads]['members']]
        self.assertEqual({self.catalog.resolve(i) for i in member_ids}, {mads})
        counts = [len(self.catalog.detail(lid)['courses']) for lid in self.catalog.labs]
        self.assertLessEqual(sorted(counts)[len(counts) // 2], 20)
        detail = self.catalog.detail(mads)
        self.assertTrue(all(c['evidence'] and c['reason'] for c in detail['courses']))

    def test_guide_reflects_selection_and_rejects_foreign_courses(self):
        lid = next(lid for lid, p in self.catalog.profiles.items() if p['professors'][0].startswith('곽수하'))
        detail = self.catalog.detail(lid)
        first = detail['courses'][0]['id']
        guide = self.catalog.guide(lid, [first])
        self.assertEqual([c['id'] for c in guide['selected_courses']], [first])
        self.assertNotEqual(guide['start_now'][0]['difficulty'], self.catalog.guide(lid, [])['start_now'][0]['difficulty'])
        with self.assertRaises(ValueError):
            self.catalog.guide(lid, ['curriculum_0001'] if 'curriculum_0001' not in {c['id'] for c in detail['courses']} else ['nope'])


if __name__ == '__main__':
    unittest.main()
