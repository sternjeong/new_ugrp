"""A fresh 50-query test set written by an isolated Sonnet that knows nothing about the engine (same type mix as the dev set)."""
import json, subprocess
from pathlib import Path
OUT = Path(__file__).parent
BASE = OUT.parent / 'engine_strategies_20261109'
dev = json.loads((BASE / 'queries.json').read_text())
COUNTS = {'keyword': 6, 'sentence': 10, 'like_dislike': 6, 'dislike_only': 4, 'course': 5, 'long': 4, 'english': 3, 'everyday': 6, 'off_topic': 3, 'procedure': 2, 'too_broad': 1}
ABOUT = {'keyword': '연구 키워드 2~4개만 나열', 'sentence': '관심을 말하는 한 문장', 'like_dislike': '좋아하는 것과 피하고 싶은 것을 함께 말함', 'dislike_only': '싫어하는 것만 말함', 'course': '들은 수업 이름으로 관심을 말함',
         'long': '두세 문장의 긴 입력(여러 조건)', 'english': '영어 또는 한영 혼합', 'everyday': '연구 용어 없이 일상적인 궁금증을 그대로 물음', 'off_topic': '연구실 탐색과 전혀 무관한 말', 'procedure': '지원·신청 절차 질문', 'too_broad': '한두 단어로 된 지나치게 넓은 입력'}
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['items'], 'properties': {'items': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['type', 'text'], 'properties': {'type': {'type': 'string', 'enum': list(COUNTS)}, 'text': {'type': 'string'}}}}}}
spec = '\n'.join(f'- {k} {v}개: {ABOUT[k]}' for k, v in COUNTS.items())
prompt = f"""포스텍 학부생이 '관심을 입력하면 연구실을 찾아 주는' 서비스의 검색창에 입력할 법한 문장을 만들어 주세요. 말투는 실제 학생처럼 다양하게, 분야는 이공계 전 학과(컴공, 전자, 기계, 산업, 화학, 화공, 신소재, 물리, 수학, 생명, 환경, 의공학, 인문사회)에 고루 퍼지게 쓰세요.

유형별 개수:
{spec}

아래 예시와 주제나 표현이 겹치지 않게 하세요.
{json.dumps([q['text'] for q in dev], ensure_ascii=False)}"""
d = json.loads(subprocess.run(['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--tools', '', '--no-session-persistence', '--output-format', 'json', '--json-schema', json.dumps(SCHEMA, separators=(',', ':'))], input=prompt, text=True, capture_output=True, cwd='/tmp', timeout=400).stdout)
items = d['structured_output']['items']
got = {k: sum(i['type'] == k for i in items) for k in COUNTS}
assert got == COUNTS, got
(OUT / 'holdout.json').write_text(json.dumps([{'id': f'h{i + 1:02d}', **x} for i, x in enumerate(items)], ensure_ascii=False, indent=1))
print('ok', len(items), d.get('total_cost_usd'))
