import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from curri.kaggle_launcher import KaggleLauncher


class KaggleLauncherTests(unittest.TestCase):
    def test_status_precedes_push_and_failure_keeps_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            notebook = root / 'worker.ipynb'
            notebook.write_text('{}')
            config = root / 'config.json'
            config.write_text(json.dumps({'notebook': str(notebook), 'kernel': 'user/worker', 'dataset': 'user/data'}))
            launcher = KaggleLauncher(config)
            with patch('curri.kaggle_launcher.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0), SimpleNamespace(returncode=1, stderr='push failed', stdout='')
            ]) as run, patch('curri.kaggle_launcher.time.monotonic', return_value=1000):
                launcher.last_attempt = 1000
                launcher._launch()
                self.assertEqual(run.call_args_list[0].args[0], ['kaggle', 'kernels', 'status', 'user/worker'])
                self.assertEqual(run.call_args_list[1].args[0][:3], ['kaggle', 'kernels', 'push'])
                self.assertIn('push failed', launcher.last_error)
                self.assertFalse(launcher.ensure_started())
                self.assertEqual(run.call_count, 2)

    def test_push_succeeds_even_if_status_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'worker.ipynb').write_text('{}')
            config = root / 'config.json'
            config.write_text(json.dumps({'notebook': str(root / 'worker.ipynb'), 'kernel': 'user/worker', 'dataset': 'user/data'}))
            launcher = KaggleLauncher(config)
            with patch('curri.kaggle_launcher.subprocess.run', side_effect=[
                SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)
            ]) as run:
                launcher._launch()
                self.assertEqual(run.call_count, 2)
                self.assertEqual(launcher.last_error, '')
