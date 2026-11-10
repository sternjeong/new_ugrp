"""Grade with the same five-judge panel the labs the service engine returned that the study never showed the panel. Run from the repo root with PYTHONPATH=.:experiments/engine_strategies_20261109"""
import concurrent.futures
import json
import random
import subprocess
from pathlib import Path

import judge as pj
from curri.curated_catalog import CuratedCatalog, load_jsonl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
papers = {r['id']: r['papers'] for r in load_jsonl(ROOT / 'data/sunwoo/papers.jsonl')}
unseen = json.loads((HERE / 'service_metrics.json').read_text())['unseen']
queries = {q['id']: q['text'] for q in json.loads((HERE / 'holdout.json').read_text())}
pools = json.loads((HERE / 'test_pools.json').read_text())
(HERE / 'service_calls').mkdir(exist_ok=True)


def ask(task):
    k, j, fresh = task
    path = HERE / 'service_calls' / f's__{k}_j{j}.json'
    if path.exists() and json.loads(path.read_text()).get('ok'):
        return json.loads(path.read_text())
    order = fresh + pools[k]['labs'][:6]
    random.Random(f's-{k}-{j}').shuffle(order)
    key = {f'L{i + 1}': l for i, l in enumerate(order)}
    body = '\n'.join(f'[{a}] ' + json.dumps(pj.card_text(catalog, papers, l), ensure_ascii=False) for a, l in key.items())
    cmd = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--tools', '', '--no-session-persistence', '--system-prompt', pj.SYSTEM, '--output-format', 'json', '--json-schema', json.dumps(pj.SCHEMA, separators=(',', ':'))]
    d = json.loads(subprocess.run(cmd, input=f'{pj.RULES}\n\n학생 입력: {queries[k]}\n\n연구실 카드:\n{body}', text=True, capture_output=True, cwd='/tmp', timeout=300).stdout)
    v = d.get('structured_output')
    ok = isinstance(v, dict) and {g['label'] for g in v['grades']} == set(key)
    r = {'ok': ok, 'key': key, 'cost': d.get('total_cost_usd'), 'value': {'grades': [g for g in v['grades'] if key[g['label']] in fresh]} if ok else None}
    path.write_text(json.dumps(r, ensure_ascii=False))
    return r


todo = [(k, j, labs) for k, labs in unseen.items() if labs for j in range(1, 6)]
with concurrent.futures.ThreadPoolExecutor(4) as pool:
    done = list(pool.map(ask, todo))
print('calls', len(done), 'ok', sum(r['ok'] for r in done), 'cost', round(sum(r.get('cost') or 0 for r in done), 2))
