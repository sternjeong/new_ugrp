"""Sonnet parse of the test set: only the A5 comparison baseline, same prompt as the dev set."""
import concurrent.futures, json, subprocess
from pathlib import Path
OUT = Path(__file__).parent
BASE = OUT.parent / 'engine_strategies_20261109'
ns = {'__file__': str(BASE / 'llm_parse.py')}
exec((BASE / 'llm_parse.py').read_text().split('qs = ')[0], ns)
SCHEMA, RULES = ns['SCHEMA'], ns['RULES']
qs = json.loads((OUT / 'holdout.json').read_text())
def call(q):
    d = json.loads(subprocess.run(['claude', '-p', '--model', 'sonnet', '--effort', 'low', '--tools', '', '--no-session-persistence', '--output-format', 'json', '--json-schema', json.dumps(SCHEMA, separators=(',', ':'))], input=RULES + '\n\n입력: ' + q['text'], text=True, capture_output=True, cwd='/tmp', timeout=200).stdout)
    return q['id'], d['structured_output'], d.get('duration_ms')
with concurrent.futures.ThreadPoolExecutor(4) as ex:
    res = list(ex.map(call, qs))
(OUT / 'llm_parse_holdout.json').write_text(json.dumps({k: {**v, 'ms': ms} for k, v, ms in res}, ensure_ascii=False, indent=1))
print('parsed', len(res))
