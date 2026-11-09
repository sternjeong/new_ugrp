"""AQ: strategy A5 with Qwen's parse. Builds rankings, judges only newly surfaced labs (with anchors), then reports.

Run from the repo root: PYTHONPATH=.:experiments/engine_strategies_20261109 python3 experiments/engine_strategies_20261109/qwen/run.py <kaggle_output_dir> {rank|judge|analyze}
"""
import concurrent.futures
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from curri.curated_catalog import COURSE_CUE, CuratedCatalog, clip
from curri.curated_query_engine import CuratedQueryEngine
from curri.query_engine import LAMBDA, zscores

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = PARENT.parents[1]
kaggle, command = Path(sys.argv[1]), sys.argv[2]
queries = json.loads((PARENT / 'queries.json').read_text())
parent_rank = json.loads((PARENT / 'rankings.json').read_text())['rankings']
pools = json.loads((PARENT / 'pools.json').read_text())
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
mean = lambda xs: sum(xs) / len(xs) if xs else None


def rank():
    parses = json.loads((kaggle / 'qwen_parse.json').read_text())['parses']
    chunk = json.loads((kaggle / 'qwen_chunk_sims.json').read_text())
    engine = CuratedQueryEngine(catalog)
    scores = lambda t: dict(zip(chunk['owners'], chunk['sims'][t]))
    out = {}
    for q in queries:
        L = parses[q['id']]
        if L['intent'] != 'search':
            out[q['id']] = None
            continue
        likes, dislikes, search = L['likes'] or [L['search_text']], [d for d in L['dislikes'] if d.strip()], L['search_text'] or q['text']
        cards = [c for c in catalog.search(search) if not engine.conflicts_with_dislikes(c['id'], dislikes)]
        cue = bool(COURSE_CUE.search(q['text']))
        courses = catalog.courses_named(likes, cue)
        linked = {l: v for l, v in catalog.course_labs(courses).items() if not engine.conflicts_with_dislikes(l, dislikes)}
        led = bool(linked) and (cue or all(catalog.courses_named([x], cue) for x in likes))
        pos = scores(search)
        labs = [l for l in pos if l in catalog.profiles]
        s = dict(zip(labs, zscores([pos[l] for l in labs])))
        for d in dislikes:
            z = dict(zip(labs, zscores([scores(d)[l] for l in labs])))
            s = {l: v - LAMBDA * max(0.0, z[l]) for l, v in s.items()}
        lists = ([[c['id'] for c in cards]] if cards else []) + [sorted(labs, key=lambda l: -s[l])]
        fused = [l for l in CuratedQueryEngine.fuse(linked, led, *lists) if not engine.conflicts_with_dislikes(l, dislikes)]
        out[q['id']] = fused[:10]
    (HERE / 'rankings.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    (HERE / 'qwen_parse.json').write_text((kaggle / 'qwen_parse.json').read_text())
    meta = json.loads((kaggle / 'qwen_parse.json').read_text())
    secs = sorted(v['seconds'] for v in parses.values())
    print('failed', [k for k, v in parses.items() if v['failed']], 'median s', secs[len(secs) // 2], 'max', secs[-1], 'load', meta['load_s'], 'gpu MB', meta['peak_gpu_mb'])
    print('intents', {i: sum(v['intent'] == i for v in parses.values()) for i in {v['intent'] for v in parses.values()}}, 'declined', [k for k, v in out.items() if not v])
    for k in ['q17', 'q38', 'q50', 'q21', 'q23', 'q43']:
        print(k, parses[k]['intent'], parses[k]['likes'], parses[k]['dislikes'], '|', parses[k]['search_text'][:70])


def old_grades():
    grades = defaultdict(lambda: defaultdict(list))
    for q in queries:
        for j in range(1, 6):
            r = json.loads((PARENT / 'calls' / f"{q['id']}_j{j}.json").read_text())
            for g in r['value']['grades']:
                grades[q['id']][r['key'][g['label']]].append(g['grade'])
    return grades


SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['should_recommend', 'grades'],
          'properties': {'should_recommend': {'type': 'boolean'}, 'grades': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['label', 'grade'],
                         'properties': {'label': {'type': 'string'}, 'grade': {'type': 'integer', 'minimum': 0, 'maximum': 3}}}}}}


def judge():
    sys.path.insert(0, str(PARENT))
    import importlib.util
    spec = importlib.util.spec_from_file_location('parent_judge', PARENT / 'judge.py')
    pj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pj)
    rankings = json.loads((HERE / 'rankings.json').read_text())
    papers = {r['id']: r['papers'] for r in map(json.loads, filter(str.strip, (ROOT / 'data/sunwoo/papers.jsonl').read_text(encoding='utf-8').splitlines()))}
    old = old_grades()
    todo = []
    for q in queries:
        ranked = (rankings[q['id']] or [])[:5]
        new = [l for l in ranked if l not in old[q['id']]]
        if not new:
            continue
        known = sorted(((mean(v), l) for l, v in old[q['id']].items()), reverse=True)
        step = max(1, len(known) // 6)
        anchors = [l for _, l in known[::step]][:6]
        cards = {l: pj.card_text(catalog, papers, l) for l in new + anchors}
        for j in range(1, 6):
            order = new + anchors
            random.Random(f"qwen-{q['id']}-{j}").shuffle(order)
            key = {f'L{i + 1}': l for i, l in enumerate(order)}
            body = '\n'.join(f'[{label}] ' + json.dumps(cards[l], ensure_ascii=False) for label, l in key.items())
            todo.append((q['id'], j, key, f"{pj.RULES}\n\n학생 입력: {q['text']}\n\n연구실 카드:\n{body}", new, anchors))
    print('calls', len(todo), 'queries with new labs', len({t[0] for t in todo}))

    def call(item):
        qid, j, key, prompt, new, anchors = item
        path = HERE / 'calls' / f'{qid}_j{j}.json'
        path.parent.mkdir(exist_ok=True)
        if path.exists() and json.loads(path.read_text()).get('ok'):
            return True
        cmd = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--tools', '', '--no-session-persistence', '--system-prompt', pj.SYSTEM,
               '--output-format', 'json', '--json-schema', json.dumps(SCHEMA, separators=(',', ':'))]
        start = time.time()
        try:
            proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, cwd='/tmp', timeout=300)
            parsed = json.loads(proc.stdout)
            value = parsed.get('structured_output')
            ok = proc.returncode == 0 and not parsed.get('is_error') and isinstance(value, dict) and {g['label'] for g in value['grades']} == set(key)
            rec = {'ok': ok, 'value': value, 'key': key, 'new': new, 'anchors': anchors, 'seconds': round(time.time() - start, 1), 'cost_usd_list': parsed.get('total_cost_usd'),
                   'error': None if ok else str(parsed.get('result') or proc.stderr)[:300]}
        except Exception as exc:
            rec = {'ok': False, 'key': key, 'new': new, 'anchors': anchors, 'error': f'{type(exc).__name__}: {exc}'[:300]}
        rec['input_sha256'] = hashlib.sha256(prompt.encode()).hexdigest()
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        os.replace(tmp, path)
        return rec['ok']

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(call, todo))
    print('ok', sum(results), '/', len(results))


def dcg(g):
    return sum(x / math.log2(i + 2) for i, x in enumerate(g))


def boot(d, reps=10000, seed=17):
    rng = random.Random(seed)
    m = sorted(mean([rng.choice(d) for _ in d]) for _ in range(reps))
    return [round(m[int(.025 * reps)], 3), round(m[int(.975 * reps) - 1], 3)]


def analyze():
    rankings = json.loads((HERE / 'rankings.json').read_text())
    meta = json.loads((HERE / 'qwen_parse.json').read_text())
    parent = json.loads((PARENT / 'metrics.json').read_text())
    should = parent['should_recommend']
    old = old_grades()
    gain = {q: {l: mean(v) for l, v in labs.items()} for q, labs in old.items()}
    anchor_new, anchor_old, added, cost, failures = defaultdict(list), [], defaultdict(lambda: defaultdict(list)), 0.0, []
    for path in sorted((HERE / 'calls').glob('*.json')):
        r = json.loads(path.read_text())
        qid = path.stem.rsplit('_j', 1)[0]
        if not r.get('ok'):
            failures.append(path.stem)
            continue
        cost += r.get('cost_usd_list') or 0
        for g in r['value']['grades']:
            lab = r['key'][g['label']]
            if lab in r['new']:
                added[qid][lab].append(g['grade'])
            else:
                anchor_new[(qid, lab)].append(g['grade'])
    pairs = [(mean(v), gain[q][l]) for (q, l), v in anchor_new.items()]
    n = len(pairs)
    mx, my = mean([a for a, _ in pairs]), mean([b for _, b in pairs])
    corr = sum((a - mx) * (b - my) for a, b in pairs) / math.sqrt(sum((a - mx) ** 2 for a, _ in pairs) * sum((b - my) ** 2 for _, b in pairs)) if n > 2 else None
    for q, labs in added.items():
        for l, v in labs.items():
            gain[q][l] = mean(v)
    NAMES = {'AQ': rankings, 'A5': parent_rank['A5'], 'A4': parent_rank['A4'], 'A0': parent_rank['A0']}
    ids = [q['id'] for q in queries]
    score, ndcg = defaultdict(dict), defaultdict(dict)
    for qid in ids:
        pool = {l: g for l, g in gain[qid].items() if l not in pools[qid]['controls']}
        ideal = dcg(sorted(pool.values(), reverse=True)[:5]) or 1.0
        for name, r in NAMES.items():
            top = (r[qid] or [])[:5]
            if should[qid]:
                nd = dcg([gain[qid].get(l, 0.0) for l in top]) / ideal if top else 0.0
                score[name][qid] = ndcg[name][qid] = nd
            else:
                score[name][qid] = 1.0 if not top else 0.0
    rec = [i for i in ids if should[i]]
    table = {n: {'fit': round(mean(list(score[n].values())), 3), 'ndcg5_recommend': round(mean([ndcg[n][i] for i in rec]), 3),
                 'correct_refusal': sum(score[n][i] == 1.0 for i in ids if not should[i]),
                 'wrong_refusal_of_recommend': sum(not (NAMES[n][i]) for i in rec)} for n in NAMES}
    def cmp(a, b, group):
        d = [score[a][i] - score[b][i] for i in group]
        return {'diff': round(mean(d), 3), 'ci95': boot(d)}
    types = defaultdict(list)
    for q in queries:
        types[q['type']].append(q['id'])
    secs = sorted(v['seconds'] for v in meta['parses'].values())
    out = {'table': table, 'AQ_minus_A5': cmp('AQ', 'A5', ids), 'AQ_minus_A0': cmp('AQ', 'A0', ids), 'AQ_minus_A4': cmp('AQ', 'A4', ids),
           'recommend_only': {'AQ_minus_A5': cmp('AQ', 'A5', rec), 'AQ_minus_A0': cmp('AQ', 'A0', rec), 'AQ_minus_A4': cmp('AQ', 'A4', rec)},
           'by_type': {t: {n: round(mean([score[n][i] for i in qs]), 3) for n in NAMES} for t, qs in types.items()},
           'anchors': {'n': n, 'mean_new_minus_old': round(mx - my, 3), 'correlation': round(corr, 3) if corr is not None else None},
           'qwen': {'model': meta['model'], 'load_s': meta['load_s'], 'peak_gpu_mb': meta['peak_gpu_mb'], 'median_s': secs[len(secs) // 2], 'p90_s': secs[int(len(secs) * .9)],
                    'parse_failures': [k for k, v in meta['parses'].items() if v['failed']], 'intents': {i: sum(v['intent'] == i for v in meta['parses'].values()) for i in {v['intent'] for v in meta['parses'].values()}}},
           'added_labs': sum(len(v) for v in added.values()), 'queries_with_new_labs': len(added), 'failures': failures, 'cost_usd_list': round(cost, 2)}
    (HERE / 'metrics.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


{'rank': rank, 'judge': judge, 'analyze': analyze}[command]()
