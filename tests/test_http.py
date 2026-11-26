import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from curri.catalog import Catalog
from curri.store import Store
from curri.server import make_server
from test_catalog import fixture
from curri.research_papers import ResearchPapers
from unittest.mock import patch


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        fixture(root)
        self.server = make_server('127.0.0.1', 0, Catalog(root), Store(root / 'app.sqlite'))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, path, data=None, origin=None):
        headers = {'Content-Type': 'application/json', 'Origin': origin or self.url}
        req = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        try:
            response = self.client.open(req)
        except urllib.error.HTTPError as exc:
            response = exc
        payload = response.read()
        return response.status, json.loads(payload) if 'application/json' in response.headers.get('Content-Type', '') else payload

    def test_home_screen_files(self):
        status, manifest = self.request('/manifest.webmanifest')
        self.assertEqual(status, 200)
        manifest = json.loads(manifest)
        self.assertEqual((manifest['display'], manifest['start_url']), ('standalone', '/?source=homescreen'))
        for icon in manifest['icons'] + [{'src': '/apple-touch-icon.png'}]:
            status, body = self.request(icon['src'])
            self.assertEqual((status, body[:8]), (200, b'\x89PNG\r\n\x1a\n'))
        status, page = self.request('/?source=homescreen')
        self.assertIn(b'rel="manifest"', page)
        self.assertIn(b'install-dialog', page)
        self.assertEqual(self.request('/install.js')[0], 200)

    def test_complete_first_exploration_signup_second_and_refresh(self):
        self.assertEqual(self.request('/api/session')[0], 200)
        status, found = self.request('/api/search', {'interests': 'AI 생명과학', 'goal': 'research'})
        self.assertEqual(status, 200)
        self.assertEqual(len(found['labs']), 2)
        status, detail = self.request('/api/explore', {'lab_id': 'bio'})
        self.assertEqual(status, 200)
        self.assertEqual(len(detail['lab']['courses']), 2)
        status, guide = self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': ['ml']})
        self.assertEqual(status, 200)
        self.assertTrue(guide['guide']['prepare_next'])
        self.assertEqual(self.request('/api/save', {'lab_id': 'bio', 'selected_ids': ['ml'], 'note': '<keep my note>', 'saved': True})[0], 200)
        self.assertEqual(self.request('/api/explore', {'lab_id': 'ai'})[0], 401)
        self.assertEqual(self.request('/api/guide', {'lab_id': 'ai', 'selected_ids': []})[0], 401)
        self.assertEqual(self.request('/api/register', {'email': 'test@example.com', 'password': 'valid-password'})[0], 400)
        account = {'real_name': '홍길동', 'nickname': '테스터', 'school': 'POSTECH', 'interest_text': 'AI와 생명과학'}
        self.assertEqual(self.request('/api/register', {'email': 'test@example.com', 'password': 'valid-password', 'consents': {'terms': True, 'privacy': True, 'age14': True}, 'account': account})[0], 200)
        self.assertTrue(self.request('/api/session')[1]['user']['profile_complete'])
        status, snapshot = self.request('/api/session')
        self.assertEqual(snapshot['explorations'][0]['note'], '<keep my note>')
        self.assertEqual(snapshot['explorations'][0]['selected_ids'], ['ml'])
        self.assertEqual(self.request('/api/explore', {'lab_id': 'ai'})[0], 200)
        self.assertEqual(self.request('/api/logout', {})[0], 200)
        self.assertIsNone(self.request('/api/session')[1]['user'])
        self.assertEqual(self.request('/api/session')[1]['explorations'], [])
        self.assertEqual(self.request('/api/login', {'email': 'test@example.com', 'password': 'valid-password'})[0], 200)
        saved = self.request('/api/session')[1]['explorations']
        self.assertEqual(next(r for r in saved if r['lab_id'] == 'bio')['note'], '<keep my note>')

    def test_confirmed_slots_follow_the_search_text(self):
        self.request('/api/session')
        self.assertEqual(self.request('/api/mirror/confirm', {'slots': [{'key': 'style', 'values': ['Python']}]})[0], 400)  # nothing searched yet
        self.request('/api/search', {'interests': 'AI 생명과학', 'goal': 'research'})
        status, saved = self.request('/api/mirror/confirm', {'slots': [{'key': 'style', 'values': [' Python ']}, {'key': 'output', 'values': ['데모']}]})
        self.assertEqual(status, 200)
        self.assertEqual([s['values'] for s in saved['confirmed_slots']], [['Python'], ['데모']])
        self.assertEqual(self.request('/api/session')[1]['profile']['confirmed_slots'], saved['confirmed_slots'])
        self.request('/api/search', {'interests': 'AI 생명과학', 'goal': 'graduate'})  # same text: kept
        self.assertEqual(self.request('/api/session')[1]['profile']['confirmed_slots'], saved['confirmed_slots'])
        self.assertEqual(self.request('/api/mirror/confirm', {'slots': [{'key': 'who_you_are', 'values': ['x']}]})[0], 400)
        self.assertEqual(self.request('/api/session')[1]['profile']['confirmed_slots'], saved['confirmed_slots'])
        self.request('/api/search', {'interests': '다른 관심 문장', 'goal': 'research'})  # new text: cleared
        self.assertNotIn('confirmed_slots', self.request('/api/session')[1]['profile'])
        self.request('/api/mirror/confirm', {'slots': [{'key': 'topic', 'values': ['AI']}]})
        self.assertEqual(self.request('/api/mirror/confirm', {'slots': []})[1], {'confirmed_slots': []})
        self.assertNotIn('confirmed_slots', self.request('/api/session')[1]['profile'])
        self.assertEqual(self.request('/api/mirror/confirm', {'slots': []}, origin='https://evil.example')[0], 403)

    def test_invalid_requests_do_not_consume_guest_slot_or_leak_files(self):
        self.request('/api/session')
        self.assertEqual(self.request('/api/explore', {'lab_id': 'bad'})[0], 404)
        self.assertIsNone(self.request('/api/session')[1]['first_lab_id'])
        self.assertEqual(self.request('/api/search', {'interests': 123})[0], 400)
        self.assertEqual(self.request('/api/explore', {'lab_id': 'bio'}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('/data/courses.jsonl')[0], 404)
        self.assertEqual(self.request('/../data/courses.jsonl')[0], 404)
        self.assertEqual(self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': ['unrelated']})[0], 400)
        self.assertIsNone(self.request('/api/session')[1]['first_lab_id'])

    def test_stale_selection_from_an_older_course_list_is_dropped_on_reopen(self):
        self.request('/api/session')
        self.assertEqual(self.request('/api/explore', {'lab_id': 'bio'})[0], 200)
        jar = next(h.cookiejar for h in self.client.handlers if hasattr(h, 'cookiejar'))
        token = next(c.value for c in jar if c.name == 'curri_session')
        # Simulate a selection saved when a different engine offered more courses for this lab.
        Store(Path(self.tmp.name) / 'app.sqlite').save_exploration(token, 'bio', ['ml', 'unrelated'], {'stale': True}, '메모', True)
        status, payload = self.request('/api/explore', {'lab_id': 'bio'})
        self.assertEqual(status, 200)
        self.assertEqual(payload['exploration']['selected_ids'], ['ml'])
        self.assertIsNone(payload['exploration']['guide'])
        self.assertEqual(payload['exploration']['stale_selection_dropped'], 1)
        self.assertEqual(payload['exploration']['note'], '메모')
        self.assertEqual(self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': ['ml']})[0], 200)
        self.assertEqual(self.request('/api/session')[1]['explorations'][0]['selected_ids'], ['ml'])

    def test_same_lab_alias_does_not_count_as_second_lab(self):
        self.request('/api/session')
        self.assertEqual(self.request('/api/explore', {'lab_id': 'bio'})[0], 200)
        self.assertEqual(self.request('/api/explore', {'lab_id': 'duplicate'})[0], 200)

    def test_guide_version_can_be_switched_and_old_guides_are_hidden(self):
        root = Path(self.tmp.name)
        papers = root / 'papers.jsonl'
        papers.write_text(json.dumps({'id': 'bio', 'papers': [
            {'openalex_id': 'W1', 'title': 'Biology research', 'year': 2025, 'abstract': 'A study.'}]}))
        flag = root / 'variant'
        server = make_server('127.0.0.1', 0, Catalog(root), Store(root / 'version.sqlite'),
                             research_papers=ResearchPapers(papers), guide_variant_file=flag)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f'http://127.0.0.1:{server.server_port}'
        self.assertEqual(self.request('/api/explore', {'lab_id': 'bio'})[1]['guide_variant'], 'A')
        self.assertEqual(self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': []})[1]['guide']['variant'], 'A')
        flag.write_text('B')
        detail = self.request('/api/explore', {'lab_id': 'bio'})[1]
        self.assertIsNone(detail['exploration']['guide'])
        self.assertEqual(detail['lab']['research_papers'][0]['id'], 'W1')
        self.assertEqual(self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': [], 'paper_ids': ['W999']})[0], 400)
        with patch.object(ResearchPapers, 'references', return_value=([], False)):
            guide = self.request('/api/guide', {'lab_id': 'bio', 'selected_ids': [], 'paper_ids': ['W1']})[1]['guide']
        self.assertEqual(guide['variant'], 'B')
        self.assertEqual(guide['research']['selected'][0]['id'], 'W1')
        flag.write_text('A')
        self.assertIsNone(self.request('/api/explore', {'lab_id': 'bio'})[1]['exploration']['guide'])
        with Store(root / 'version.sqlite').db() as db:
            counts = {(r['variant'], r['event']): r['count'] for r in db.execute('SELECT * FROM guide_variant_counts')}
        self.assertEqual(counts, {('A', 'explore'): 2, ('A', 'guide'): 1, ('B', 'explore'): 1, ('B', 'guide'): 1})
