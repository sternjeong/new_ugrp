"""R7 LLM query rewrite (engine-modules branch, docs/plans/2026-11-22-engine-modules.md).

Two gaps the rules cannot close:
- Lab texts are mostly English and written by researchers; students write Korean everyday words
  ('배터리 오래 가게 하는 거'). The model rewrites a liked phrase as the English technical terms a lab page
  would use ('battery degradation, cycle life, state of health'), and the engine scores the phrase and the
  rewrite and keeps whichever matches a lab better.
- The model names the conditions of a phrase that asks for several things at once ('딥러닝 이용한 의학 연구'),
  and the engine requires every one of them (AND).

The phrase goes to the AI worker's queue (curri/llm_jobs.py, kind 'query': `claude -p --model haiku` on the dev
VM), which serves these before guides and summaries. A search waits at most WAIT seconds; a slower answer is
kept in llm_jobs and used from the next search on, so a phrase costs one call. Without the worker, or for a
student who did not consent to processing abroad, the phrase is searched as written.
"""
import re
import time

from ..llm_jobs import QuotaExceeded, cache_key

KIND = 'query'
PROMPT_VERSION = 'query.v1'
MODEL, EFFORT = 'haiku', 'low'
WAIT = 12.0  # seconds a search waits for a new phrase's rewrite
MAX_FACETS = 3
MAX_PHRASE = 80  # a longer phrase is a sentence fragment the parser could not split; it is searched as written
SCHEMA = {'type': 'object', 'properties': {
    'english': {'type': 'string', 'description': 'the phrase as 3-8 English technical terms a lab page would use, comma separated'},
    'facets': {'type': 'array', 'items': {'type': 'string'}, 'description': 'conditions a matching lab must meet; [] for one condition'},
}, 'required': ['english', 'facets'], 'additionalProperties': False}
SYSTEM = '''학생이 연구실 검색창에 쓴 관심 구절을 검색용으로 바꿔요. 연구실 자료는 대부분 영어 논문 제목과 연구 소개예요.

- english: 이 구절을 연구실 자료에서 쓸 법한 영어 전문 용어 3–8개로 바꿔 쉼표로 이어요. 일상어는 분야 용어로 바꿔요(예: "배터리 오래 가게" → battery degradation, cycle life). 구절에 없는 분야를 더하지 않아요.
- facets: 구절이 서로 다른 조건 둘 이상을 함께 요구하면(방법과 대상, 대상과 목적 등) 조건마다 짧은 한국어 구절과 영어 용어를 함께 써요(예: "딥러닝 deep learning", "의학 medicine clinical"). 조건이 하나면 빈 목록이에요. 최대 3개.
- 연구실·교수 이름은 지어내지 않아요.'''
NOTHING = {'english': '', 'facets': []}


def clean(raw, phrase):
    english = re.sub(r'\s+', ' ', str(raw.get('english') or '')).strip()[:200]
    facets = [re.sub(r'\s+', ' ', str(f)).strip()[:80] for f in raw.get('facets') or []]
    facets = [f for f in dict.fromkeys(facets) if f and f != phrase][:MAX_FACETS]
    if len(facets) < 2:
        facets = []  # one condition is the phrase itself
    return {'english': english if english.lower() != phrase.lower() else '', 'facets': facets}


def validate(payload, raw):
    if not isinstance(raw, dict):
        raise ValueError('결과 형식 오류')
    return clean(raw, payload['phrase'])


class LlmQuery:
    def __init__(self, jobs, wait=WAIT, sleep=time.sleep):
        self.jobs, self.wait, self.sleep = jobs, wait, sleep
        self.memo = {}
        jobs.register(KIND, validate)

    @staticmethod
    def key(phrase):
        return cache_key(KIND, PROMPT_VERSION, MODEL, phrase)

    def __call__(self, phrase, remote=True):
        """{'english', 'facets'} for a liked phrase; no rewrite when the worker cannot answer in time. remote=False
        (no consent to processing abroad, or this client's hourly rewrites are used up) uses only answers already made."""
        phrase = re.sub(r'\s+', ' ', (phrase or '').strip())
        if phrase in self.memo:
            return self.memo[phrase]
        if len(phrase) > MAX_PHRASE:
            return dict(NOTHING)
        job = self.jobs.get(key=self.key(phrase))
        if (job is None or job['status'] == 'failed') and remote and self.jobs.online():
            try:
                job = self.jobs.submit(KIND, self.key(phrase), {'phrase': phrase, 'system': SYSTEM, 'prompt': phrase, 'schema': SCHEMA,
                                                               'model': MODEL, 'effort': EFFORT})
            except QuotaExceeded:
                job = None
        deadline = time.time() + (self.wait if remote else 0)
        while job is not None and job['status'] in ('queued', 'running') and time.time() < deadline:
            self.sleep(0.25)
            job = self.jobs.get(job_id=job['id'])
        if job is None or job['status'] != 'done' or not isinstance(job['result'], dict):
            return dict(NOTHING)
        self.memo[phrase] = job['result']
        if len(self.memo) > 4096:
            self.memo.pop(next(iter(self.memo)))
        return job['result']
