"""Durable LLM job queue served to a pull worker (a `claude -p` loop running in tmux on the dev VM).

The server never calls a model itself. It stores each job with a cache key; identical requests reuse the done job.
A worker long-polls `/api/llm/poll`, runs the prompt with the JSON schema it was given and posts `/api/llm/answer`.
Jobs claimed but not answered within LEASE seconds go back to the queue. Search query rewrites (kind 'query',
curri/rag/query_llm.py) go first because a search waits for them, then guides, then summaries.
"""
import hashlib
import hmac
import json
import threading
import time

LEASE = 600
MAX_ATTEMPTS = 2
ONLINE_WINDOW = 90
# New jobs per kind over the last 24 hours, for the whole service: the worker runs on one Claude subscription,
# so a script or a crowd must not use it up. A cached answer (same key) never counts.
DAILY_LIMIT = {'query': 2000, 'guide': 400, 'summary': 400}


class QuotaExceeded(RuntimeError):
    """The daily limit for this kind of job is reached."""


def cache_key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]


class LLMJobs:
    def __init__(self, store, token=None):
        self.store, self.token = store, token
        self.cond = threading.Condition()
        self.last_poll = 0.0
        self.validators = {}
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS llm_jobs (
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, cache_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL, started REAL, finished REAL, seconds REAL, cost REAL);
            CREATE INDEX IF NOT EXISTS llm_jobs_status ON llm_jobs(status, id);
            ''')

    def enabled(self):
        return bool(self.token)

    def online(self):
        return self.enabled() and time.time() - self.last_poll < ONLINE_WINDOW

    def check_token(self, header):
        return self.enabled() and isinstance(header, str) and hmac.compare_digest(header, f'Bearer {self.token}')

    def register(self, kind, validator):
        """validator(payload, raw_result) -> cleaned result; raises ValueError when the answer can't be used."""
        self.validators[kind] = validator

    @staticmethod
    def _public(row):
        if row is None:
            return None
        return {'id': row['id'], 'kind': row['kind'], 'status': row['status'],
                'result': json.loads(row['result']) if row['result'] else None, 'error': row['error']}

    def submit(self, kind, key, payload):
        """Queue a job unless the same key is already queued, running or done. Failed jobs are retried once more.
        Raises QuotaExceeded when a new job of this kind would pass DAILY_LIMIT."""
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM llm_jobs WHERE cache_key=?', (key,)).fetchone()
            if row and (row['status'] != 'failed' or row['attempts'] >= MAX_ATTEMPTS):
                return self._public(row)
            limit = DAILY_LIMIT.get(kind)
            if not row and limit is not None and db.execute('SELECT COUNT(*) FROM llm_jobs WHERE kind=? AND created>?',
                                                            (kind, now - 86400)).fetchone()[0] >= limit:
                raise QuotaExceeded(kind)
            if row:
                db.execute("UPDATE llm_jobs SET status='queued', error=NULL, started=NULL WHERE id=?", (row['id'],))
                job_id = row['id']
            else:
                job_id = db.execute("INSERT INTO llm_jobs(kind,cache_key,payload,status,created) VALUES (?,?,?,'queued',?)",
                                    (kind, key, json.dumps(payload, ensure_ascii=False), now)).lastrowid
            row = db.execute('SELECT * FROM llm_jobs WHERE id=?', (job_id,)).fetchone()
        with self.cond:
            self.cond.notify_all()
        return self._public(row)

    def get(self, job_id=None, key=None):
        with self.store.db() as db:
            row = (db.execute('SELECT * FROM llm_jobs WHERE id=?', (job_id,)) if job_id is not None else
                   db.execute('SELECT * FROM llm_jobs WHERE cache_key=?', (key,))).fetchone()
        return self._public(row)

    def _claim(self):
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE llm_jobs SET status='queued' WHERE status='running' AND started<?", (now - LEASE,))
            row = db.execute("SELECT * FROM llm_jobs WHERE status='queued' ORDER BY (kind!='query'), (kind='summary'), id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE llm_jobs SET status='running', started=?, attempts=attempts+1 WHERE id=?", (now, row['id']))
        return {'id': row['id'], 'kind': row['kind'], **json.loads(row['payload'])}

    def poll(self, wait=25.0):
        self.last_poll = time.time()
        deadline = time.time() + max(0.0, min(float(wait), 30.0))
        while True:
            job = self._claim()
            if job or time.time() >= deadline:
                return job
            with self.cond:
                self.cond.wait(min(5.0, max(0.0, deadline - time.time())))
            self.last_poll = time.time()

    def answer(self, body):
        job_id, ok = body.get('job_id'), body.get('ok')
        if type(job_id) is not int or not isinstance(ok, bool):
            raise ValueError('job_id와 ok가 필요합니다.')
        with self.store.db() as db:
            row = db.execute("SELECT * FROM llm_jobs WHERE id=? AND status='running'", (job_id,)).fetchone()
        if row is None:
            return {'accepted': False}
        status, result, error = 'failed', None, str(body.get('error') or '')[:300] or None
        if ok:
            try:
                validator = self.validators.get(row['kind'], lambda payload, raw: raw)
                result = validator(json.loads(row['payload']), body.get('result'))
                status, error = 'done', None
            except (ValueError, KeyError, TypeError) as exc:
                error = f'검증 실패: {exc}'[:300]
        if status == 'failed' and row['attempts'] < MAX_ATTEMPTS:
            status = 'queued'  # one more try
        with self.store.db() as db:
            db.execute('UPDATE llm_jobs SET status=?, result=?, error=?, finished=?, seconds=?, cost=? WHERE id=?',
                       (status, json.dumps(result, ensure_ascii=False) if result is not None else None, error, time.time(),
                        body.get('seconds') if isinstance(body.get('seconds'), (int, float)) else None,
                        body.get('cost') if isinstance(body.get('cost'), (int, float)) else None, job_id))
        return {'accepted': True, 'status': status}

    def stats(self):
        with self.store.db() as db:
            counts = {r['status']: r['n'] for r in db.execute('SELECT status, COUNT(*) n FROM llm_jobs GROUP BY status')}
            recent = [dict(r) for r in db.execute('SELECT id, kind, status, error, attempts, seconds, cost, created FROM llm_jobs ORDER BY id DESC LIMIT 30')]
        return {'online': self.online(), 'last_poll': self.last_poll, 'counts': counts, 'recent': recent}
