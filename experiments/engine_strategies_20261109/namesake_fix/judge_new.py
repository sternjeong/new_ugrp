"""Grade labs newly in the top 5 after the engine change, with the panel and anchors of the Qwen re-experiment; then compare old vs new."""
import concurrent.futures, importlib.util, json, math, random, subprocess, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, '.')
from curri.curated_catalog import CuratedCatalog
S, OUT = Path(sys.argv[1]), Path('experiments/engine_strategies_20261109')  # S holds new_a0.json (rankings_after.json) and fix_calls/
spec = importlib.util.spec_from_file_location('pj', OUT / 'judge.py'); pj = importlib.util.module_from_spec(spec); spec.loader.exec_module(pj)
catalog = CuratedCatalog('data/sunwoo')
papers = {r['id']: r['papers'] for r in map(json.loads, filter(str.strip, open('data/sunwoo/papers.jsonl', encoding='utf-8')))}
Q = json.load(open(OUT / 'queries.json')); old = json.load(open(OUT / 'rankings.json'))['rankings']['A0']; new = json.load(open(S / 'new_a0.json')); pools = json.load(open(OUT / 'pools.json'))
gr, votes = defaultdict(lambda: defaultdict(list)), defaultdict(list)
for q in Q:
    for j in range(1, 6):
        r = json.load(open(OUT / 'calls' / f"{q['id']}_j{j}.json")); votes[q['id']].append(r['value']['should_recommend'])
        for g in r['value']['grades']: gr[q['id']][r['key'][g['label']]].append(g['grade'])
mean = lambda v: sum(v) / len(v)
todo = []
for q in Q:
    k = q['id']; fresh = [l for l in (new[k] or [])[:5] if l not in gr[k]]
    if not fresh or sum(votes[k]) <= 2: continue
    known = sorted(((mean(v), l) for l, v in gr[k].items()), reverse=True); anchors = [l for _, l in known[::max(1, len(known) // 6)]][:6]
    cards = {l: pj.card_text(catalog, papers, l) for l in fresh + anchors}
    for j in range(1, 6):
        order = fresh + anchors; random.Random(f"fix-{k}-{j}").shuffle(order); key = {f'L{i + 1}': l for i, l in enumerate(order)}
        body = '\n'.join(f'[{a}] ' + json.dumps(cards[l], ensure_ascii=False) for a, l in key.items())
        todo.append((k, j, key, f"{pj.RULES}\n\n학생 입력: {q['text']}\n\n연구실 카드:\n{body}", fresh))
print('calls', len(todo), flush=True)
def call(t):
    k, j, key, prompt, fresh = t; p = S / 'fix_calls' / f'{k}_j{j}.json'; p.parent.mkdir(exist_ok=True)
    if p.exists(): return json.loads(p.read_text())
    cmd = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--tools', '', '--no-session-persistence', '--system-prompt', pj.SYSTEM, '--output-format', 'json', '--json-schema', json.dumps(pj.SCHEMA, separators=(',', ':'))]
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, cwd='/tmp', timeout=300); d = json.loads(proc.stdout); v = d.get('structured_output')
    r = {'ok': bool(v) and {g['label'] for g in v['grades']} == set(key), 'value': v, 'key': key, 'fresh': fresh, 'cost': d.get('total_cost_usd')}; p.write_text(json.dumps(r, ensure_ascii=False)); return r
with concurrent.futures.ThreadPoolExecutor(3) as pool: results = list(pool.map(call, todo))
print('ok', sum(r['ok'] for r in results), '/', len(results), 'cost', round(sum(r.get('cost') or 0 for r in results), 2))
extra = defaultdict(lambda: defaultdict(list))
for t, r in zip(todo, results):
    if r['ok']:
        for g in r['value']['grades']:
            if r['key'][g['label']] in t[4]: extra[t[0]][r['key'][g['label']]].append(g['grade'])
dcg = lambda g: sum(x / math.log2(i + 2) for i, x in enumerate(g))
A, B, rows = [], [], []
for q in Q:
    k = q['id']
    if sum(votes[k]) <= 2: continue
    g = {l: mean(v) for l, v in gr[k].items()}; g.update({l: mean(v) for l, v in extra[k].items()})
    ideal = dcg(sorted((v for l, v in g.items() if l not in pools[k]['controls']), reverse=True)[:5]) or 1
    a = dcg([g.get(l, 0) for l in (old[k] or [])[:5]]) / ideal; b = dcg([g.get(l, 0) for l in (new[k] or [])[:5]]) / ideal
    A.append(a); B.append(b); rows.append((round(b - a, 3), k, q['text'][:30], {catalog.profiles[l]['professors'][0]: round(mean(v), 1) for l, v in extra[k].items()}))
d = [b - a for a, b in zip(A, B)]; rng = random.Random(7); ms = sorted(mean([rng.choice(d) for _ in d]) for _ in range(10000))
print('recommend queries', len(A), 'old', round(mean(A), 3), 'new', round(mean(B), 3), 'diff', round(mean(d), 3), 'ci95', round(ms[250], 3), round(ms[9749], 3))
rows.sort(); print(*rows[:5], sep='\n'); print(*rows[-4:], sep='\n')
