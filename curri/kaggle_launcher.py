"""Start a private Kaggle embedding notebook when the first search needs it."""
import json
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class KaggleLauncher:
    def __init__(self, config_file):
        self.config = json.loads(Path(config_file).read_text(encoding='utf-8'))
        self.lock = threading.Lock()
        self.last_attempt = 0.0
        self.running = False
        self.last_error = ''

    def ensure_started(self):
        """Return whether a launch is in progress. Never run Kaggle CLI on an HTTP thread."""
        with self.lock:
            if self.running:
                return True
            if time.monotonic() - self.last_attempt < 600:
                return not self.last_error
            self.last_attempt = time.monotonic()
            self.running = True
            threading.Thread(target=self._launch, daemon=True).start()
            return True

    def _launch(self):
        try:
            cfg = self.config
            with tempfile.TemporaryDirectory(prefix='curri-kaggle-') as directory:
                stage = Path(directory)
                notebook = Path(cfg['notebook'])
                (stage / notebook.name).write_bytes(notebook.read_bytes())
                metadata = {'id': cfg['kernel'], 'title': cfg['kernel'].split('/')[-1],
                            'code_file': notebook.name, 'language': 'python',
                            'kernel_type': 'notebook', 'is_private': True,
                            'enable_gpu': True, 'enable_internet': True,
                            'dataset_sources': [cfg['dataset']],
                            'competition_sources': [], 'kernel_sources': []}
                (stage / 'kernel-metadata.json').write_text(json.dumps(metadata), encoding='utf-8')
                # The CLI refreshes expired OAuth credentials during status, before push needs them.
                subprocess.run([cfg.get('kaggle_bin', 'kaggle'), 'kernels', 'status', cfg['kernel']],
                               capture_output=True, text=True, timeout=120)
                result = subprocess.run([cfg.get('kaggle_bin', 'kaggle'), 'kernels', 'push', '-p', str(stage)],
                                        capture_output=True, text=True, timeout=120)
                if result.returncode:
                    raise RuntimeError((result.stderr or result.stdout)[-500:])
            self.last_error = ''
        except Exception as exc:
            self.last_error = str(exc)
            print(f'Kaggle 워커 시작 실패: {self.last_error}', flush=True)
        finally:
            with self.lock:
                self.running = False
