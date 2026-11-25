"""tools/paper_attribution.py: the review queue, carrying a reviewed decision through every file, and the check that
fails when a decision is missing downstream. Synthetic data, no network."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_curated_profiles  # noqa: E402
import paper_attribution as pa  # noqa: E402

MIXED, CLEAN = 'lab_mixed', 'lab_clean'


def paper(wid, title, subfield='Software', **extra):
    return {'openalex_id': wid, 'doi': f'10.1000/{wid.lower()}', 'title': title, 'year': 2024, 'date': '2024-01-01',
            'venue': 'Venue', 'subfield': subfield, 'cited_by_count': 3, 'lab_led': True, 'in_list': False,
            'postech_affiliation': False, 'cited_on_site': False, 'abstract': 'An abstract about ' + title,
            'abstract_source': 'openalex', 'versions': [], 'reasons': ['fill'], **extra}


def lab(lab_id, name, author_ids):
    return {'id': lab_id, 'recommendable': True, 'status': 'verified',
            'professor': {'name_ko': name, 'name_en': 'Gildong Hong', 'departments': ['컴퓨터공학과']},
            'lab': {'name': name + ' 연구실', 'url': 'https://lab.example/'},
            'intro': {'text': 'We study programming languages.', 'source_url': 'https://lab.example/'},
            'research_areas': [{'name': 'Programming Languages', 'name_en': 'Programming Languages', 'kind': 'area'}],
            'openalex': {'status': 'verified', 'author_ids': author_ids,
                         'profiles': [{'id': i, 'flag': None, 'verdict': 'confirmed'} for i in author_ids], 'raw_author_ids': []}}


def work(wid, title, authors, doi=None):
    """An OpenAlex work as the API returns it. authors: (raw name, profile id or None, orcid or None, ror)."""
    return {'id': f'https://openalex.org/{wid}', 'doi': f'https://doi.org/{doi or "10.1000/" + wid.lower()}', 'title': title,
            'publication_year': 2025, 'publication_date': '2025-06-05', 'type': 'article', 'is_retracted': False,
            'abstract_inverted_index': {'A': [0], 'framework': [1]}, 'fwci': 1.0, 'cited_by_count': 2,
            'primary_topic': {'display_name': 'Topic', 'subfield': {'display_name': 'Software'}},
            'primary_location': {'source': {'display_name': 'Journal', 'type': 'journal'}},
            'authorships': [{'author_position': 'last' if i == len(authors) - 1 else 'first', 'raw_author_name': name,
                             'is_corresponding': i == len(authors) - 1,
                             'author': {'id': f'https://openalex.org/{aid}' if aid else None, 'display_name': name,
                                        'orcid': f'https://orcid.org/{orcid}' if orcid else None},
                             'institutions': [{'display_name': 'Some University', 'ror': f'https://ror.org/{ror}'}]}
                            for i, (name, aid, orcid, ror) in enumerate(authors)]}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'data'
        (self.root / 'curation').mkdir(parents=True)
        self.cache = Path(self.tmp.name) / 'cache'
        labs = [lab(MIXED, '홍길동', ['A1']), lab(CLEAN, '김철수', ['A2']),
                {**lab('lab_out', '제외', []), 'recommendable': False}]
        bundles = [{'id': MIXED, 'professor': '홍길동', 'author_ids': ['A1'], 'basis': 'lab_led', 'core_topics': [], 'areas_matched': [],
                    'counts': {}, 'papers': [paper('W1', 'Lattice physics of a namesake', 'Nuclear and High Energy Physics'),
                                             paper('W2', 'Tourism study of a namesake', 'Tourism', versions=['W20']),
                                             paper('W3', 'A type system for effects')]},
                   {'id': CLEAN, 'professor': '김철수', 'author_ids': ['A2'], 'basis': 'lab_led', 'core_topics': [], 'areas_matched': [],
                    'counts': {}, 'papers': [paper('W5', 'A calculus of modules', in_list=True)]}]
        self.write_lines('labs.jsonl', labs)
        self.write_lines('papers.jsonl', bundles)
        by_id = {b['id']: b for b in bundles}
        self.write_lines('app_profiles.jsonl', [build_curated_profiles.profile(row, by_id[row['id']]) for row in labs if row['recommendable']])
        self.write_lines('courses.jsonl', [{'code': 'CSED101'}])
        self.write_lines('final_labs.jsonl', [{'advisor_id': MIXED, 'professor_papers': [{'title': 'An execution framework for big data engines', 'year': 2025}]}])
        (self.root / 'curation/paper_identity.jsonl').write_text(
            json.dumps({'rules': 'identity-v1', 'labs': []}) + '\n' +
            ''.join(json.dumps({'lab_id': lid, 'work_id': wid, 'status': status}) + '\n'
                    for lid, wid, status in ((MIXED, 'W1', 'held'), (MIXED, 'W2', 'held'), (MIXED, 'W3', 'held'), (CLEAN, 'W5', 'confirmed'))))
        (self.root / 'curation/lab_overrides.json').write_text('{}\n')
        self.write_json('lab_course_bge_m3.json', {'model': 'm', 'sources': {'app_profiles.jsonl': self.sha('app_profiles.jsonl'), 'courses.jsonl': self.sha('courses.jsonl')},
                                                   'labs': {MIXED: {'CSED101': 0.5}, CLEAN: {'CSED101': 0.6}},
                                                   'migration': {'requires_recompute': [], 'retained_profile_sha256': {}}})
        self.write_json('IMPORT_MANIFEST.json', {'files': [{'path': n, 'bytes': (self.root / n).stat().st_size, 'sha256': self.sha(n)}
                                                           for n in ('labs.jsonl', 'papers.jsonl', 'curation/lab_overrides.json')],
                                                 'derived_files': [{'path': n, 'sha256': self.sha(n)} for n in ('app_profiles.jsonl', 'lab_course_bge_m3.json')]}, indent=2)

    def tearDown(self):
        self.tmp.cleanup()

    def sha(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def write_lines(self, name, rows):
        (self.root / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')

    def write_json(self, name, value, indent=None):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False, indent=indent) + '\n', encoding='utf-8')

    def decide(self, lab_id, **decision):
        self.write_json('curation/lab_overrides.json', {lab_id: decision}, indent=1)

    def exclusion(self, wid, **extra):
        titles = {'W1': 'Lattice physics of a namesake', 'W2': 'Tourism study of a namesake', 'W3': 'A type system for effects'}
        return {'openalex_id': wid, 'doi': f'10.1000/{wid.lower()}', 'title': titles.get(wid, 'x'), 'severity': 'P0', 'checked_at': '2026-11-24',
                'reason': 'the paper names another institution for this author', 'sources': ['https://publisher.example/paper'], **extra}

    def rows(self, name):
        return [json.loads(line) for line in (self.root / name).read_text(encoding='utf-8').splitlines()]

    def save_work(self, w):
        (self.cache / 'works').mkdir(parents=True, exist_ok=True)
        (self.cache / 'works' / (w['id'].rsplit('/', 1)[-1] + '.json')).write_text(json.dumps(w))

    def apply(self, lab_id=MIXED):
        return pa.apply(pa.Data(self.root), lab_id, fetch=self.no_network, cache=self.cache, offline=True, today='2026-11-24')

    def no_network(self, url):
        raise AssertionError('network used: ' + url)


class AuditTests(Fixture):
    def test_a_lab_with_no_confirmed_paper_comes_first(self):
        rows = {r['lab_id']: r for r in pa.audit(pa.Data(self.root))}
        self.assertEqual((rows[MIXED]['tier'], rows[MIXED]['unverified']), (1, 3))
        self.assertEqual((rows[CLEAN]['tier'], rows[CLEAN]['confirmed']), (0, 1))
        self.assertNotIn('lab_out', rows)
        self.assertEqual([r['lab_id'] for r in pa.audit_report(pa.Data(self.root))['queue']], [MIXED])

    def test_an_affiliation_or_title_mention_is_not_identity(self):
        bundles = self.rows('papers.jsonl')
        for p in bundles[0]['papers']:
            p['postech_affiliation'], p['cited_on_site'] = True, True  # a namesake can work at the same school (D-19)
        self.write_lines('papers.jsonl', bundles)
        self.assertEqual({r['lab_id']: r for r in pa.audit(pa.Data(self.root))}[MIXED]['unverified'], 3)

    def test_a_reviewed_paper_counts_as_reviewed(self):
        bundles = self.rows('papers.jsonl')
        bundles[0]['papers'][2]['ownership_verification'] = {'basis': 'official_publication_list'}
        self.write_lines('papers.jsonl', bundles)
        row = {r['lab_id']: r for r in pa.audit(pa.Data(self.root))}[MIXED]
        self.assertEqual((row['reviewed'], row['unverified'], row['tier']), (1, 2, 3))


class DecisionTests(Fixture):
    def test_an_exclusion_needs_its_reason_and_sources(self):
        bare = {'openalex_id': 'W1', 'doi': '10.1000/w1', 'title': 'x', 'severity': 'P0', 'checked_at': '2026-11-24', 'reason': 'r'}
        self.assertTrue(pa.decision_errors(MIXED, {'paper_exclusions': [bare]}))
        self.assertTrue(pa.decision_errors(MIXED, {'paper_exclusions': [{**bare, 'sources': ['http://insecure.example']}]}))
        self.assertTrue(pa.decision_errors(MIXED, {'paper_exclusions': [{**self.exclusion('W1'), 'severity': 'P1'}]}))
        self.assertEqual(pa.decision_errors(MIXED, {'paper_exclusions': [self.exclusion('W1')]}), [])

    def test_a_paper_cannot_be_both_excluded_and_allowed(self):
        allow = {'orcid': None, 'checked_at': 't', 'scope': 's', 'works': [
            {'openalex_id': 'W1', 'doi': '10.1000/w1', 'title': 'x', 'author_name': 'Gildong Hong', 'source': 'https://lab.example/pubs'}]}
        self.assertTrue(pa.decision_errors(MIXED, {'paper_exclusions': [self.exclusion('W1')], 'paper_allowlist': allow}))

    def test_apply_refuses_an_undocumented_decision_and_writes_nothing(self):
        self.decide(MIXED, paper_exclusions=[{'openalex_id': 'W1', 'doi': '10.1000/w1', 'title': 'x', 'severity': 'P0'}])
        before = self.sha('papers.jsonl')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.sha('papers.jsonl'), before)


class ApplyExclusionTests(Fixture):
    def test_exclusions_are_removed_everywhere_and_nothing_else_moves(self):
        self.decide(MIXED, paper_exclusions=[self.exclusion('W1'), self.exclusion('W99', doi='10.1000/w2', aliases=[{'openalex_id': 'W20', 'doi': '10.1000/w2'}])])
        clean_lines = {name: [l for l in (self.root / name).read_text().splitlines() if CLEAN in l or 'lab_out' in l]
                       for name in ('labs.jsonl', 'papers.jsonl', 'app_profiles.jsonl')}
        result = self.apply()
        self.assertEqual((result['papers'], result['basis']), (1, 'unverified_after_exclusions'))
        bundle = self.rows('papers.jsonl')[0]
        self.assertEqual([p['openalex_id'] for p in bundle['papers']], ['W3'])  # W2 went by its DOI and its version id
        profile = self.rows('app_profiles.jsonl')[0]
        self.assertEqual([t['label_ko'] for t in profile['topics'] if t['section'] == 'representative_paper'], ['A type system for effects'])
        self.assertEqual(profile['paper_basis'], 'unverified_after_exclusions')
        self.assertEqual(self.rows('labs.jsonl')[0]['openalex']['paper_exclusions'][0]['openalex_id'], 'W1')
        for name, lines in clean_lines.items():  # the other records keep their bytes
            self.assertEqual([l for l in (self.root / name).read_text().splitlines() if CLEAN in l or 'lab_out' in l], lines)
        mapping = json.loads((self.root / 'lab_course_bge_m3.json').read_text())
        self.assertNotIn(MIXED, mapping['labs'])  # scores of the old profile text are not reused
        self.assertIn(CLEAN, mapping['labs'])
        self.assertEqual(mapping['migration']['requires_recompute'], [MIXED])
        self.assertEqual(mapping['sources']['app_profiles.jsonl'], self.sha('app_profiles.jsonl'))  # or the server drops every score
        manifest = json.loads((self.root / 'IMPORT_MANIFEST.json').read_text())
        self.assertEqual({e['path'] for e in manifest['corrected_files']}, {'labs.jsonl', 'papers.jsonl', 'curation/lab_overrides.json'})
        self.assertEqual(manifest['corrections'], [{'date': '2026-11-24', 'tool': 'tools/paper_attribution.py apply', 'lab_ids': [MIXED]}])
        self.assertEqual(pa.check(pa.Data(self.root)), [])

    def test_applying_twice_changes_nothing(self):
        self.decide(MIXED, paper_exclusions=[self.exclusion('W1')])
        self.apply()
        names = ('labs.jsonl', 'papers.jsonl', 'app_profiles.jsonl', 'lab_course_bge_m3.json', 'IMPORT_MANIFEST.json')
        first = [self.sha(n) for n in names]
        self.apply()
        self.assertEqual([self.sha(n) for n in names], first)

    def test_an_excluded_id_with_another_doi_stops_the_run(self):
        self.decide(MIXED, paper_exclusions=[self.exclusion('W1', doi='10.1000/other')])
        before = self.sha('papers.jsonl')
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.sha('papers.jsonl'), before)


class ApplyAllowlistTests(Fixture):
    def allow(self, **work_extra):
        return {'orcid': '0009-0000-0000-0001', 'checked_at': '2026-11-24T00:00:00+00:00', 'scope': 'two reviewed papers',
                'works': [{'openalex_id': 'W7', 'doi': '10.1000/w7', 'title': 'An execution framework for big data engines',
                           'author_id': None, 'author_name': 'Gildong Hong', 'observed_orcid': '0009-0000-0000-0001',
                           'basis': 'publisher_orcid_and_affiliation', 'source': 'https://api.crossref.org/works/10.1000/w7', **work_extra}]}

    def test_a_paper_outside_every_profile_is_added_by_the_name_on_the_paper(self):
        self.save_work(work('W7', 'An execution framework for big data engines',
                            [('Student Kim', 'A9', None, 'other'), ('Gildong Hong', None, '0009-0000-0000-0001', pa.POSTECH_ROR)]))
        self.decide(MIXED, openalex_author_ids=[], paper_exclusions=[self.exclusion('W1'), self.exclusion('W2'), self.exclusion('W3')], paper_allowlist=self.allow())
        result = self.apply()
        self.assertEqual((result['papers'], result['basis']), (1, 'official_allowlist'))
        bundle = self.rows('papers.jsonl')[0]
        p = bundle['papers'][0]
        self.assertEqual((p['openalex_id'], p['lab_led'], p['postech_affiliation'], p['in_list']), ('W7', True, True, True))
        self.assertEqual(p['abstract'], 'A framework')
        self.assertEqual(p['ownership_verification']['orcid_status'], 'match')
        self.assertEqual(p['ownership_verification']['basis'], 'publisher_orcid_and_affiliation')
        self.assertEqual(bundle['author_ids'], [])  # the merged profile is no longer followed for new papers (D-21)
        openalex = self.rows('labs.jsonl')[0]['openalex']
        self.assertEqual((openalex['author_ids'], openalex['raw_author_ids'], openalex['status']), ([], ['A1'], 'corrected'))
        self.assertEqual(pa.check(pa.Data(self.root)), [])
        row = {r['lab_id']: r for r in pa.audit(pa.Data(self.root))}[MIXED]
        self.assertEqual((row['reviewed'], row['unverified'], row['tier']), (1, 0, 0))

    def test_a_record_that_changed_since_the_review_stops_the_run(self):
        self.decide(MIXED, paper_allowlist=self.allow())
        for changed in (work('W7', 'An execution framework for big data engines', [('Gildong Hong', None, '0009-0000-0000-0001', 'x')], doi='10.1000/moved'),
                        work('W7', 'A different title', [('Gildong Hong', None, '0009-0000-0000-0001', 'x')]),
                        work('W7', 'An execution framework for big data engines', [('Gildong Hong', None, '0000-0000-0000-9999', 'x')]),
                        work('W7', 'An execution framework for big data engines', [('Someone Else', None, None, 'x')]),
                        work('W7', 'An execution framework for big data engines', [('Gildong Hong', None, '0009-0000-0000-0001', 'x'), ('Gildong Hong', 'A3', '0009-0000-0000-0001', 'x')])):
            self.save_work(changed)
            before = [self.sha(n) for n in ('labs.jsonl', 'papers.jsonl', 'app_profiles.jsonl')]
            with self.assertRaises(ValueError):
                self.apply()
            self.assertEqual([self.sha(n) for n in ('labs.jsonl', 'papers.jsonl', 'app_profiles.jsonl')], before)

    def test_without_network_a_missing_work_stops_the_run(self):
        self.decide(MIXED, paper_allowlist=self.allow())
        with self.assertRaises(ValueError):
            self.apply()


class CheckTests(Fixture):
    def applied(self):
        self.decide(MIXED, paper_exclusions=[self.exclusion('W1')])
        self.apply()

    def test_a_decision_recorded_but_not_applied_is_reported(self):
        self.decide(MIXED, paper_exclusions=[self.exclusion('W1')])
        problems = '\n'.join(pa.check(pa.Data(self.root)))
        self.assertIn('labs.jsonl의 paper_exclusions', problems)
        self.assertIn('W1이 papers.jsonl에 남아', problems)
        self.assertIn('app_profiles.jsonl에 남아', problems)

    def test_an_excluded_paper_that_comes_back_is_reported(self):
        self.applied()
        bundles = self.rows('papers.jsonl')
        bundles[0]['papers'].append(paper('W8', 'Renamed copy', doi='10.1000/w1'))  # a regenerated selection, new id but the same DOI
        self.write_lines('papers.jsonl', bundles)
        self.assertTrue(any('W8' in p for p in pa.check(pa.Data(self.root))))

    def test_a_profile_built_from_older_papers_is_reported(self):
        self.applied()
        profiles = self.rows('app_profiles.jsonl')
        profiles[1]['topics'] = [t for t in profiles[1]['topics'] if t['section'] != 'representative_paper']
        self.write_lines('app_profiles.jsonl', profiles)
        self.assertTrue(any('김철수' in p and '대표 논문' in p for p in pa.check(pa.Data(self.root))))

    def test_a_stale_course_link_hash_is_reported(self):
        self.applied()
        mapping = json.loads((self.root / 'lab_course_bge_m3.json').read_text())
        mapping['sources']['app_profiles.jsonl'] = '0' * 64
        self.write_json('lab_course_bge_m3.json', mapping)
        self.assertTrue(any('과목 유사도 전체' in p for p in pa.check(pa.Data(self.root))))

    def test_the_feed_must_not_follow_a_dropped_profile(self):
        self.decide(MIXED, openalex_author_ids=[], paper_exclusions=[self.exclusion('W1')])
        self.apply()
        bundles = self.rows('papers.jsonl')
        bundles[0]['author_ids'] = ['A1']
        self.write_lines('papers.jsonl', bundles)
        self.assertTrue(any('author_ids' in p for p in pa.check(pa.Data(self.root))))


class EvidenceTests(Fixture):
    def test_the_sheet_shows_what_the_paper_says_and_finds_listed_papers_outside_the_profile(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if 'api.crossref.org' in url:
                return {'message': {'author': [{'given': 'Gildong', 'family': 'Hong', 'ORCID': 'https://orcid.org/0000-0000-0000-9999',
                                                'affiliation': [{'name': 'Another Hospital'}]}]}}
            if 'title.search' in url:
                return {'results': [work('W7', 'An execution framework for big data engines', [('Gildong Hong', None, None, pa.POSTECH_ROR)])]}
            if 'author.id' in url:
                return {'meta': {'count': 3}, 'results': [work(w, 't', [('Gildong Hong', 'A1', None, 'other')]) for w in ('W1', 'W2', 'W3')]}
            return {'results': [work(w, 't', [('Gildong Hong', 'A1', None, 'other')]) for w in ('W1', 'W2', 'W3')]}

        report = pa.evidence(pa.Data(self.root), MIXED, fetch=fetch, cache=self.cache)
        self.assertEqual([r['evidence'] for r in report['papers']], ['unverified'] * 3)
        self.assertEqual(report['papers'][0]['stated'][0]['institutions'], ['Some University'])
        self.assertFalse(report['papers'][0]['stated'][0]['postech'])
        self.assertEqual(report['papers'][0]['crossref'], {'orcid': '0000-0000-0000-9999', 'affiliations': ['Another Hospital']})
        self.assertEqual(report['profiles'][0]['institutions'], 1)
        self.assertEqual([c['openalex_id'] for c in report['school_list_candidates']], ['W7'])
        self.assertTrue(report['school_list_candidates'][0]['stated'][0]['postech'])
        self.assertFalse(any('mailto' in u for u in calls))  # no contact address leaves the machine


class RepositoryDataTests(unittest.TestCase):
    def test_every_recorded_decision_is_in_force(self):
        self.assertEqual(pa.check(pa.Data()), [])

    def test_the_reviewed_labs_show_only_reviewed_papers(self):
        rows = {r['lab_id']: r for r in pa.audit(pa.Data())}
        for lab_id, count in (('0a6ff7bc33b7ed4911d691f6ab0c5136', 2), ('f99a04f1c7ba3fe4f420c343e9c9a1ca', 7),
                              ('9c2741540c4286d26221b8f2701304f2', 7), ('00a2f37dcd22c6860346daa192299452', 7)):
            self.assertEqual((rows[lab_id]['reviewed'], rows[lab_id]['unverified'], rows[lab_id]['tier']), (count, 0, 0))


if __name__ == '__main__':
    unittest.main()
