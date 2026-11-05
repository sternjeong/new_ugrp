"""임베딩 워커: GPU가 있는 곳(Kaggle 노트북 등)에서 돌며 서비스 서버의 질의 임베딩 요청을 처리한다.

Kaggle은 외부에서 들어오는 연결을 받을 수 없으므로 워커가 서버로 먼저 접속한다.
  GET  {base_url}/api/worker/poll?wait=20   → {"job": {"id": 1, "phrases": [...]} | null}   (Authorization: Bearer 토큰)
  POST {base_url}/api/worker/answer          ← {"job_id", "lab_ids", "sims": {구절: [연구실별 유사도]}, "best": {구절: [연구실별 가장 가까운 주제 번호]}}

연구실 문서(요약 + 주제별 "라벨: 원문 인용")는 experiments의 방식과 같고, 연구실 점수는 문서별 코사인 유사도의 최대값이다.
설정은 worker_config.json: {"base_url", "token", "idle_exit_min", "max_run_min"}. 토큰은 서버의 .local/worker_token과 같아야 한다.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np


def load_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def build_docs(profiles):
    """서버가 쓰는 연구실 목록(insufficient 제외)과 같은 순서로 문서를 만든다."""
    labs = [p for p in profiles if p.get('status') != 'insufficient']
    lab_ids, docs, topic_of, starts = [], [], [], []
    for p in labs:
        lab_ids.append(p['lab_id'])
        starts.append(len(docs))
        if p.get('summary_ko'):
            docs.append(p['summary_ko'])
            topic_of.append(-1)
        for i, t in enumerate(p['topics']):
            docs.append(f"{t['label_ko']}: {t['quote'][:400]}")
            topic_of.append(i)
    return lab_ids, docs, topic_of, starts


def score(E, D, starts, topic_of):
    """E: (구절 수, 차원), D: (문서 수, 차원), 둘 다 정규화. → (연구실별 최대 유사도, 연구실별 가장 가까운 주제 번호)"""
    S = E @ D.T
    sims = np.maximum.reduceat(S, np.array(starts), axis=1)
    ends = list(starts[1:]) + [S.shape[1]]
    best = np.full(sims.shape, -1, dtype=int)
    for li, (a, b) in enumerate(zip(starts, ends)):
        cols = [k for k in range(a, b) if topic_of[k] >= 0]
        if cols:
            arg = S[:, cols].argmax(axis=1)
            best[:, li] = [topic_of[cols[j]] for j in arg]
    return sims, best


class Worker:
    def __init__(self, base_url, token, encode, profiles, idle_exit_min=20, max_run_min=240, log=print, cache_path=None, model_id=''):
        self.base, self.token, self.encode, self.log = base_url.rstrip('/'), token, encode, log
        # 0 이하는 제한 없음(전용 서버에서 상시 실행)
        self.idle_exit = idle_exit_min * 60 if idle_exit_min > 0 else float('inf')
        self.max_run = max_run_min * 60 if max_run_min > 0 else float('inf')
        self.poll_wait = 20
        self.lab_ids, docs, self.topic_of, self.starts = build_docs(profiles)
        t0 = time.time()
        key = hashlib.sha256((model_id + '\n' + '\n'.join(docs)).encode()).hexdigest()
        cached = None
        if cache_path and os.path.exists(cache_path):
            try:
                with np.load(cache_path) as z:
                    if str(z['key']) == key:
                        cached = z['D']
            except Exception:
                cached = None
        if cached is not None:
            self.D = cached.astype(np.float32)
            self.log(f'연구실 {len(self.lab_ids)}곳, 문서 {len(docs)}개 임베딩을 캐시에서 불러옴 {time.time() - t0:.1f}s')
        else:
            self.D = np.asarray(encode(docs), dtype=np.float32)
            if cache_path:
                np.savez(cache_path, key=key, D=self.D)
            self.log(f'연구실 {len(self.lab_ids)}곳, 문서 {len(docs)}개 임베딩 {time.time() - t0:.1f}s')

    def http(self, method, path, body=None, timeout=45):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json', 'User-Agent': 'curri-embed-worker/1'})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())

    def answer_for(self, phrases):
        E = np.asarray(self.encode(phrases), dtype=np.float32)
        sims, best = score(E, self.D, self.starts, self.topic_of)
        return ({p: [round(float(x), 5) for x in row] for p, row in zip(phrases, sims)},
                {p: [int(x) for x in row] for p, row in zip(phrases, best)})

    def run(self):
        start = last_job = time.time()
        jobs = 0
        self.log(f'워커 시작: {self.base} (유휴 종료 {'없음' if self.idle_exit == float('inf') else f'{self.idle_exit / 60:g}분'}, 최대 {'없음' if self.max_run == float('inf') else f'{self.max_run / 60:g}분'})')
        while True:
            now = time.time()
            if now - start > self.max_run:
                self.log('최대 실행 시간에 도달해 종료합니다.')
                break
            if now - last_job > self.idle_exit:
                self.log('요청이 없어 종료합니다(GPU 쿼터 절약).')
                break
            try:
                job = self.http('GET', f'/api/worker/poll?wait={self.poll_wait}').get('job')
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 404):
                    self.log(f'서버가 워커를 거부했습니다({exc.code}). 토큰·주소를 확인하세요. 종료합니다.')
                    break
                self.log(f'poll 오류 {exc.code}; 5초 후 재시도')
                time.sleep(5)
                continue
            except Exception as exc:           # 네트워크 일시 오류
                self.log(f'poll 실패: {type(exc).__name__}; 5초 후 재시도')
                time.sleep(5)
                continue
            if not job:
                continue
            t0 = time.time()
            try:
                sims, best = self.answer_for(job['phrases'])
                accepted = self.http('POST', '/api/worker/answer', {'job_id': job['id'], 'lab_ids': self.lab_ids, 'sims': sims, 'best': best}).get('accepted')
            except Exception as exc:
                self.log(f'작업 {job.get("id")} 처리 실패: {type(exc).__name__}: {exc}')
                continue
            jobs += 1
            last_job = time.time()
            self.log(f'작업 {job["id"]}: 구절 {len(job["phrases"])}개, {time.time() - t0:.2f}s, 서버 수락={accepted}')
        self.log(f'종료: 처리한 작업 {jobs}건, 실행 {(time.time() - start) / 60:.1f}분')
        return jobs


def main(config_path='worker_config.json', profiles_path='app_profiles.jsonl'):
    import torch
    from sentence_transformers import SentenceTransformer
    cfg = json.load(open(config_path, encoding='utf-8'))
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cpu':
        torch.set_num_threads(os.cpu_count() or 2)
    model = SentenceTransformer('BAAI/bge-m3', device=device)
    if device == 'cuda':
        model.half()
    encode = lambda texts: model.encode(list(texts), batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    print('장치:', device)
    worker = Worker(cfg['base_url'], cfg['token'], encode, load_jsonl(profiles_path), cfg.get('idle_exit_min', 20), cfg.get('max_run_min', 240),
                    cache_path=cfg.get('doc_cache') or None, model_id=f'bge-m3-{device}')
    # 시작 전에 서버 연결을 확인한다(토큰은 출력하지 않는다)
    print('서버 상태:', urllib.request.urlopen(cfg['base_url'].rstrip('/') + '/api/engine', timeout=20).read().decode())
    worker.run()


if __name__ == '__main__':
    main(*sys.argv[1:])
