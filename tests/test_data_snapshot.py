"""Contracts for the final service using the reviewed sunwoo snapshot."""
import hashlib
import json
from pathlib import Path
import unittest

from curri.curated_catalog import CuratedCatalog
from curri.research_papers import ResearchPapers

DATA = Path(__file__).resolve().parents[1] / 'data' / 'sunwoo'
# 박성우, 최영준 (2026-11-05, 2026-11-24) and 박상돈, 이승우 (2026-11-25): papers changed by a reviewed decision
CHANGED = {'0a6ff7bc33b7ed4911d691f6ab0c5136', 'f99a04f1c7ba3fe4f420c343e9c9a1ca',
           '9c2741540c4286d26221b8f2701304f2', '00a2f37dcd22c6860346daa192299452'}


def rows(name, key):
    return {row[key]: row for row in map(json.loads, (DATA / name).read_text().splitlines())}


class DataSnapshotTests(unittest.TestCase):
    def test_imported_files_match_pinned_snapshot(self):
        manifest = json.loads((DATA / 'IMPORT_MANIFEST.json').read_text())
        self.assertEqual(manifest['source_commit'], '5159843302a8e698110cd3060cde0c29dfa8943e')
        # Files corrected after the import (tools/paper_attribution.py apply) are pinned to their reviewed state instead.
        corrected = {entry['path']: entry for entry in manifest.get('corrected_files', [])}
        self.assertEqual(set(corrected), {'curation/lab_overrides.json', 'labs.jsonl', 'papers.jsonl'})
        for entry in manifest['files']:
            entry = corrected.get(entry['path'], entry)
            with self.subTest(path=entry['path']):
                content = (DATA / entry['path']).read_bytes()
                self.assertEqual(len(content), entry['bytes'])
                self.assertEqual(hashlib.sha256(content).hexdigest(), entry['sha256'])

    def test_final_only_independent_files_are_preserved(self):
        manifest = json.loads((DATA / 'IMPORT_MANIFEST.json').read_text())
        self.assertTrue(manifest['preserved_final_files'])
        for entry in manifest['derived_files']:
            self.assertEqual(hashlib.sha256((DATA / entry['path']).read_bytes()).hexdigest(), entry['sha256'])
        for entry in manifest['preserved_final_files']:
            self.assertEqual(hashlib.sha256((DATA / entry['path']).read_bytes()).hexdigest(), entry['sha256'])

    def test_corrected_papers_reach_the_service(self):
        papers = rows('papers.jsonl', 'id')
        self.assertEqual(sum(len(r['papers']) for r in papers.values()), 2757)
        actual = ResearchPapers(DATA / 'papers.jsonl')
        for lid in CHANGED:
            self.assertEqual({p['id'] for p in actual.recent(lid)}, {p['openalex_id'] for p in papers[lid]['papers']})
        self.assertIn('W4408244118', actual.labs['f99a04f1c7ba3fe4f420c343e9c9a1ca'])
        self.assertNotIn('W4323275631', actual.labs['f99a04f1c7ba3fe4f420c343e9c9a1ca'])
        # 박성우 (2026-11-24): the four remaining namesake papers are gone, his own two are in, and the merged
        # profile is no longer followed for new-paper notices.
        park = '0a6ff7bc33b7ed4911d691f6ab0c5136'
        self.assertEqual(set(actual.labs[park]), {'W4411064901', 'W2144482530'})
        self.assertEqual(papers[park]['author_ids'], [])
        # 박상돈 (2026-11-25): the KAIST and National Security Research Institute namesakes' papers are gone.
        sangdon = actual.labs['9c2741540c4286d26221b8f2701304f2']
        self.assertEqual(len(sangdon), 7)
        self.assertTrue({'W4401252814', 'W4226217787', 'W3000480525', 'W4386375303', 'W4403385480'}.isdisjoint(sangdon))
        self.assertNotIn('W4240977029', actual.labs['00a2f37dcd22c6860346daa192299452'])  # 이승우: the law paper

    def test_profile_paper_evidence_comes_from_current_papers(self):
        papers = rows('papers.jsonl', 'id')
        profiles = rows('app_profiles.jsonl', 'lab_id')
        for lid in CHANGED:
            expected = [p['title'][:100] for p in papers[lid]['papers'][:5]]
            actual = [t['label_ko'] for t in profiles[lid]['topics'] if t['section'] == 'representative_paper']
            self.assertEqual(actual, expected)
            self.assertEqual(profiles[lid]['paper_basis'], papers[lid]['basis'])

    def test_only_unchanged_course_similarities_are_reused(self):
        mapping = json.loads((DATA / 'lab_course_bge_m3.json').read_text())
        self.assertEqual(set(mapping['migration']['requires_recompute']), CHANGED)
        self.assertTrue(CHANGED.isdisjoint(mapping['labs']))
        self.assertEqual(len(mapping['labs']), 303)
        for name, digest in mapping['sources'].items():
            self.assertEqual(hashlib.sha256((DATA / name).read_bytes()).hexdigest(), digest)
        retained = mapping['migration']['retained_profile_sha256']
        self.assertEqual(set(retained), set(mapping['labs']))
        for line in (DATA / 'app_profiles.jsonl').read_bytes().splitlines(keepends=True):
            lid = json.loads(line)['lab_id']
            if lid in retained:
                self.assertEqual(hashlib.sha256(line).hexdigest(), retained[lid])
        catalog = CuratedCatalog(DATA)
        self.assertEqual(catalog.course_similarity, mapping['labs'])
        self.assertEqual(len(catalog.labs), 307)
