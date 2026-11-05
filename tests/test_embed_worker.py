"""워커 ↔ 서버 프로토콜 시험. 모델 대신 글자 3-gram 해시 벡터를 쓰므로 GPU·torch 없이 돈다(numpy 필요)."""
import hashlib
import http.cookiejar
import importlib.util
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

try:
    import numpy as np
except ImportError:      # 서비스 서버에는 numpy가 없다. 개발 VM의 venv에서만 실행
    np = None

from curri.embed_broker import EmbedBroker
from curri.profile_catalog import ProfileCatalog
from curri.query_engine import QueryEngine
from curri.server import make_server
from curri.store import Store

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo' / 'legacy' / 'mvp-4dept'


def hashed(texts, dim=256):
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, text in enumerate(texts):
        t = text.lower()
        for j in range(len(t) - 2):
            out[i, int(hashlib.md5(t[j:j + 3].encode()).hexdigest(), 16) % dim] += 1
    return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)


@unittest.skipUnless(np is not None and (DATA / 'courses.jsonl').exists(), 'numpy와 MVP 데이터가 필요합니다')
class EmbedWorkerTests(unittest.TestCase):
    def test_worker_serves_the_search_api_end_to_end(self):
        spec = importlib.util.spec_from_file_location('embed_worker', ROOT / 'tools' / 'embed_worker' / 'worker.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        catalog = ProfileCatalog(DATA)
        broker = EmbedBroker('worker-test-token')
        server = make_server('127.0.0.1', 0, catalog, Store(Path(tmp.name) / 'app.sqlite'), engine=QueryEngine(catalog, broker), broker=broker)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}'
        profiles = module.load_jsonl(DATA / 'lab_profiles.jsonl')
        logs = []
        worker = module.Worker(url, 'worker-test-token', hashed, profiles, idle_exit_min=1, max_run_min=2, log=logs.append)
        worker.poll_wait = 1
        threading.Thread(target=worker.run, daemon=True).start()
        time.sleep(1.5)
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def post(body):
            req = urllib.request.Request(url + '/api/search', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            return json.loads(client.open(req, timeout=30).read())

        self.assertEqual(json.loads(client.open(url + '/api/engine').read()), {'embedding': True})
        found = post({'interests': '로봇이 스스로 주변을 인식하고 움직이는 게 신기해요', 'goal': 'explore'})
        self.assertEqual((found['intent'], found['mode']), ('search', 'embedding'))
        self.assertTrue(found['labs'])
        for card in found['labs']:
            self.assertIn('evidence', card)
        semantic = [c for c in found['labs'] if c.get('connection') == 'semantic']
        for card in semantic:         # 의미 검색으로만 찾은 카드는 원문 인용(근거)을 가져야 한다
            self.assertTrue(card['evidence'] and card['evidence'][0]['text'], card['id'])
        for _ in range(40):          # 워커의 로그 기록은 서버 응답보다 조금 늦을 수 있다
            if any('작업' in line for line in logs):
                break
            time.sleep(0.05)
        self.assertTrue(any('작업' in line for line in logs))
        # 싫어함이 있는 질의도 워커를 거친다
        found = post({'interests': '로봇은 싫은데 컴퓨터 구조는 좋아요', 'goal': 'explore'})
        self.assertEqual(found['interpretation'], {'likes': ['컴퓨터 구조'], 'dislikes': ['로봇']})
        self.assertEqual(found['mode'], 'embedding')


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(np is not None and (DATA / 'courses.jsonl').exists(), 'numpy와 MVP 데이터가 필요합니다')
class WorkerOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('embed_worker2', ROOT / 'tools' / 'embed_worker' / 'worker.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.profiles = cls.module.load_jsonl(DATA / 'lab_profiles.jsonl')

    def test_zero_limits_mean_unlimited(self):
        worker = self.module.Worker('http://x', 't', hashed, self.profiles, idle_exit_min=0, max_run_min=0, log=lambda *_: None)
        self.assertEqual((worker.idle_exit, worker.max_run), (float('inf'), float('inf')))

    def test_document_embeddings_are_cached_and_invalidated_by_model_id(self):
        calls = []

        def counting(texts):
            calls.append(len(texts))
            return hashed(texts)
        with tempfile.TemporaryDirectory() as tmp:
            cache = str(Path(tmp) / 'docs.npz')
            first = self.module.Worker('http://x', 't', counting, self.profiles, log=lambda *_: None, cache_path=cache, model_id='m1')
            second = self.module.Worker('http://x', 't', counting, self.profiles, log=lambda *_: None, cache_path=cache, model_id='m1')
            self.assertEqual(len(calls), 1)                                  # 두 번째는 캐시
            self.assertTrue(np.allclose(first.D, second.D))
            self.module.Worker('http://x', 't', counting, self.profiles, log=lambda *_: None, cache_path=cache, model_id='m2')
            self.assertEqual(len(calls), 2)                                  # 모델이 다르면 다시 계산
