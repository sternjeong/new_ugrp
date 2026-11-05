import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from curri.store import Store, LoginRequired, InvalidCredentials


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'test.sqlite')
        self.token = self.store.session(None)

    def test_first_lab_reopens_but_second_requires_login_and_failed_attempt_does_not_replace_it(self):
        self.store.open_lab(self.token, 'first')
        self.store.open_lab(self.token, 'first')
        with self.assertRaises(LoginRequired):
            self.store.open_lab(self.token, 'second')
        self.assertEqual(self.store.snapshot(self.token)['first_lab_id'], 'first')

    def test_concurrent_open_only_grants_one_guest_lab(self):
        def enter(lab):
            try:
                self.store.open_lab(self.token, lab)
                return True
            except LoginRequired:
                return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(enter, ['a', 'b']))
        self.assertEqual(sum(results), 1)

    def test_save_cannot_bypass_gate_and_guest_cannot_read_someone_else(self):
        self.store.open_lab(self.token, 'a')
        self.store.save_exploration(self.token, 'a', ['ml'], {'topic': 'real'}, 'my note', True)
        with self.assertRaises(LoginRequired):
            self.store.save_exploration(self.token, 'b', [], {}, 'bypass', True)
        other = self.store.session(None)
        self.assertEqual(self.store.snapshot(other)['explorations'], [])
        self.assertEqual(self.store.snapshot(self.token)['explorations'][0]['note'], 'my note')

    def test_registration_rotates_session_preserves_guest_work_and_unlocks_second(self):
        self.store.open_lab(self.token, 'a')
        self.store.set_profile(self.token, {'interests': '생명과학 AI', 'goal': 'explore'})
        self.store.save_exploration(self.token, 'a', ['ml'], {'topic': 'real'}, 'keep', True)
        new = self.store.authenticate(self.token, 'Student@EXAMPLE.com', 'a-good-password', register=True)
        self.assertNotEqual(new, self.token)
        self.assertIsNone(self.store.get_session(self.token))
        snapshot = self.store.snapshot(new)
        self.assertEqual(snapshot['user']['email'], 'student@example.com')
        self.assertEqual(snapshot['profile']['interests'], '생명과학 AI')
        self.assertEqual(snapshot['explorations'][0]['selected_ids'], ['ml'])
        self.assertEqual(snapshot['explorations'][0]['note'], 'keep')
        self.store.open_lab(new, 'b')

    def test_invalid_login_does_not_consume_or_destroy_guest_state(self):
        registered = self.store.authenticate(self.token, 'x@example.com', 'a-good-password', register=True)
        guest = self.store.session(None)
        self.store.open_lab(guest, 'a')
        with self.assertRaises(InvalidCredentials):
            self.store.authenticate(guest, 'x@example.com', 'not-the-password')
        self.assertEqual(self.store.snapshot(guest)['first_lab_id'], 'a')
        self.assertTrue(self.store.snapshot(registered)['user'])

    def test_login_conflict_keeps_both_versions_and_profile_survives_new_session(self):
        account = self.store.authenticate(self.token, 'x@example.com', 'a-good-password', register=True)
        self.store.set_profile(account, {'interests': 'AI', 'goal': 'research'})
        self.store.save_exploration(account, 'a', [], {'old': True}, 'old', True)
        guest = self.store.session(None)
        self.store.save_exploration(guest, 'a', ['ml'], {'new': True}, 'new', True)
        current = self.store.authenticate(guest, 'x@example.com', 'a-good-password')
        saved = self.store.snapshot(current)['explorations'][0]
        self.assertEqual(saved['note'], 'new')
        self.assertEqual(saved['previous_versions'][0]['note'], 'old')
        self.assertEqual(self.store.snapshot(current)['profile']['interests'], 'AI')
