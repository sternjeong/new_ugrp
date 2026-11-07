"""임베딩 워커(예: Kaggle GPU 노트북)와 서버 사이의 중계.

Kaggle 노트북은 외부에서 들어오는 연결을 받을 수 없으므로, 워커가 서버로 먼저 접속한다.
  워커 → GET  /api/worker/poll    : 처리할 작업이 생길 때까지 최대 N초 기다렸다가(long-poll) 작업을 가져감
  워커 → POST /api/worker/answer  : 구절별 연구실 유사도를 돌려줌
서버는 요청 처리 중 `request()`로 작업을 올리고 결과를 기다린다. 워커가 없거나 늦으면 None을 돌려주고 호출자는 사전 검색으로 후퇴한다.
"""
import hmac
import itertools
import json
import threading
import time
from collections import OrderedDict, deque

MAX_PHRASES = 12
MAX_PHRASE_CHARS = 300


class EmbedBroker:
    def __init__(self, token, alive_seconds=45, cache_size=2000, store=None):
        self.token = token or ''
        self.store = store
        self.alive_seconds = alive_seconds
        self.cache_size = cache_size
        self.cache = OrderedDict()      # 구절 -> {'sims': {lab_id: float}, 'best': {lab_id: topic index}}
        self.cond = threading.Condition()
        self.pending = deque()
        self.waiting = {}               # job id -> {'event': Event, 'result': dict | None}
        self.ids = itertools.count(1)
        self.last_poll = 0.0
        if store is not None:
            # 계산한 구절 유사도를 DB에 남겨 재시작 뒤에도, 워커가 꺼져 있어도 같은 표현은 바로 의미 검색한다.
            with store.db() as db:
                db.execute('CREATE TABLE IF NOT EXISTS phrase_sims (phrase TEXT PRIMARY KEY, value TEXT NOT NULL, created REAL NOT NULL)')
                for row in db.execute('SELECT phrase, value FROM phrase_sims ORDER BY created DESC LIMIT ?', (cache_size,)).fetchall()[::-1]:
                    self.cache[row['phrase']] = json.loads(row['value'])

    def cached(self, phrases):
        with self.cond:
            return all(p in self.cache for p in phrases if p and p.strip())

    # ---- 인증과 상태 ----
    def enabled(self):
        return bool(self.token)

    def check_token(self, header):
        if not self.token or not header or not header.startswith('Bearer '):
            return False
        return hmac.compare_digest(header[7:].strip().encode(), self.token.encode())

    def available(self):
        return self.enabled() and time.time() - self.last_poll < self.alive_seconds

    # ---- 서버 요청 처리 쪽 ----
    def request(self, phrases, timeout=6.0, remote=True):
        """phrases의 {구절: {'sims':…, 'best':…}}를 돌려준다. 워커가 없거나 시간 초과면 None. remote=False면 캐시만 쓴다."""
        phrases = list(dict.fromkeys(p for p in phrases if p and p.strip()))
        if not phrases or len(phrases) > MAX_PHRASES:
            return None
        with self.cond:
            found = {p: self.cache[p] for p in phrases if p in self.cache}
            for p in found:
                self.cache.move_to_end(p)
        missing = [p[:MAX_PHRASE_CHARS] for p in phrases if p not in found]
        if not missing:
            return found
        if not remote or not self.available():
            return None
        job_id = next(self.ids)
        slot = {'event': threading.Event(), 'result': None}
        with self.cond:
            if len(self.pending) >= 50:
                return None
            self.waiting[job_id] = slot
            self.pending.append({'id': job_id, 'phrases': missing})
            self.cond.notify_all()
        ok = slot['event'].wait(timeout)
        with self.cond:
            self.waiting.pop(job_id, None)
            self.pending = deque(j for j in self.pending if j['id'] != job_id)
        if not ok or slot['result'] is None:
            return None
        found.update(slot['result'])
        return found

    # ---- 워커 쪽 ----
    def poll(self, wait=20.0):
        """작업 하나를 돌려준다(없으면 None). 호출 자체가 워커 생존 신호다."""
        deadline = time.time() + max(0.0, min(wait, 25.0))
        with self.cond:
            self.last_poll = time.time()
            while not self.pending:
                left = deadline - time.time()
                if left <= 0:
                    self.last_poll = time.time()
                    return None
                self.cond.wait(left)
                self.last_poll = time.time()
            return self.pending.popleft()

    def answer(self, job_id, lab_ids, sims, best):
        """sims: {구절: [연구실 순서대로 유사도]}, best: {구절: [연구실 순서대로 가장 가까운 주제 번호(없으면 -1)]}"""
        if not isinstance(lab_ids, list) or not isinstance(sims, dict) or not isinstance(best, dict):
            raise ValueError('answer 형식 오류')
        result = {}
        for phrase, row in sims.items():
            brow = best.get(phrase)
            if not isinstance(row, list) or len(row) != len(lab_ids) or not isinstance(brow, list) or len(brow) != len(lab_ids):
                raise ValueError('유사도 길이가 연구실 수와 다릅니다.')
            result[phrase] = {'sims': {lid: float(s) for lid, s in zip(lab_ids, row)},
                              'best': {lid: int(b) for lid, b in zip(lab_ids, brow)}}
        with self.cond:
            slot = self.waiting.get(job_id)
            for phrase, value in result.items():
                self.cache[phrase] = value
                self.cache.move_to_end(phrase)
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
        if self.store is not None and result:
            with self.store.db() as db:
                db.executemany('INSERT OR REPLACE INTO phrase_sims(phrase,value,created) VALUES (?,?,?)',
                               [(p, json.dumps(v), time.time()) for p, v in result.items()])
        if slot is None:
            return False
        slot['result'] = result
        slot['event'].set()
        return True
