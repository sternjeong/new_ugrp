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
        self.assertEqual(self.request('/api/register', {'email': 'test@example.com', 'password': 'valid-password', 'account': account})[0], 200)
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
