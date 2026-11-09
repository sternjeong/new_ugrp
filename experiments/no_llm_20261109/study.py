"""Pick the no-LLM search on the dev set, then compare it with A0/A4/A5 once on the test set.

Run from the repo root:
PYTHONPATH=.:experiments/no_llm_20261109:experiments/engine_strategies_20261109 python3 experiments/no_llm_20261109/study.py <kaggle_dir> <proto_dir> <vectors.f32> select|test|analyze
"""
import concurrent.futures
import importlib.util
import json
import math
import random
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import grades
from curri.curated_catalog import COURSE_CUE, CuratedCatalog, load_jsonl
from curri.curated_query_engine import CuratedQueryEngine
from curri.query_engine import LAMBDA, zscores
from forms import forms

HERE = Path(__file__).resolve().parent
kaggle, proto, vector_path, command = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
AVOID_ONLY = re.compile(r'피하고\s*싶')
POSITIVE = re.compile(r'좋|재밌|관심|궁금|는데|지만')
W = np.array([1.0, 0.3, 0.15])
LAB_KINDS = {'profile', 'intro', 'paper'}

catalog = CuratedCatalog(grades.ROOT / 'data/sunwoo')
engine = CuratedQueryEngine(catalog, None)
spec = importlib.util.spec_from_file_location('pj', grades.BASE / 'judge.py')
pj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pj)
papers = {r['id']: r['papers'] for r in load_jsonl(grades.ROOT / 'data/sunwoo/papers.jsonl')}

store = np.load(kaggle / 'dense.npz')
meta = json.loads((kaggle / 'dense_meta.json').read_text())
lexical = json.loads((kaggle / 'lexical.json').read_text())
reranks = json.loads((kaggle / 'rerank.json').read_text())
translations = json.loads((kaggle / 'translations.json').read_text())['translations']
nli = json.loads((kaggle / 'nli.json').read_text())
doc = json.loads((kaggle / 'doc_sims.json').read_text())
doc_table = {p: {'sims': dict(zip(doc['lab_ids'], doc['sims'][p])), 'best': dict(zip(doc['lab_ids'], doc['best'][p]))} for p in doc['sims']}
query_vector = dict(zip(store['texts'].tolist(), store['q']))
vocab, exemplar_vectors, d2q_vectors = store['vocab'], store['exemplars'], store['d2q']
if (kaggle / 'd2q_dense.npz').exists():  # the Doc2Query index came from a second job
    d2q_vectors = np.load(kaggle / 'd2q_dense.npz')['d2q']
    extra = json.loads((kaggle / 'd2q_lexical.json').read_text())
    meta.update(d2q_owner=extra['d2q_owner'], d2q_docs=extra['d2q_docs'])
    lexical['sparse_d2q'] = extra['sparse_d2q']
HAS_Q = len(d2q_vectors) > 0

chunks = load_jsonl(proto / 'data/rag/pack300-whole/chunks.jsonl')
V = np.fromfile(vector_path, dtype='<f4').reshape(len(chunks), -1)
owners = meta['owners']
index = {o: np.array([i for i, c in enumerate(chunks) if c['owner'] == o and c['kind'] in LAB_KINDS]) for o in owners}
known = [o for o in owners if o in catalog.profiles]
d2q_index = defaultdict(list)
for i, o in enumerate(meta['d2q_owner']):
    d2q_index[o].append(i)
exemplar_class = [c for c, xs in json.loads((HERE / 'intent_exemplars.json').read_text()).items() for _ in xs]


memo_forms, memo_search, memo_links, memo_dense = {}, {}, {}, {}


def cached(store_, key, make):
    if key not in store_:
        store_[key] = make()
    return store_[key]


def aggregate(sims, table):
    out = {}
    for o in known:
        top = np.sort(sims[table[o]])[::-1][:3] if len(table[o]) else np.zeros(0)
        out[o] = float((W[:len(top)] * top).sum())
    return out


def unit(v):
    return v / np.linalg.norm(v)


def expanded(v, cfg):
    if cfg.get('C'):
        v = unit(v + cfg['C'] * vocab[np.argsort(vocab @ v)[::-1][:5]].mean(0))
    if cfg.get('P'):
        v = unit(v + cfg['P'] * V[np.argsort(V @ v)[::-1][:10]].mean(0))
    return v


def ranked(scores, penalties):
    labs = list(scores)
    z = dict(zip(labs, zscores([scores[l] for l in labs])))
    for p in penalties:
        pz = dict(zip(labs, zscores([p[l] for l in labs])))
        z = {l: s - LAMBDA * max(0.0, pz[l]) for l, s in z.items()}
    return sorted(labs, key=lambda l: -z[l])


def as_labs(values):
    return {o: v for o, v in zip(owners, values) if o in catalog.profiles}


def class_margin(v, skip=None):
    """Best refusing class minus 'search', each class scored by the mean of its three closest exemplars."""
    sims = exemplar_vectors @ v
    if skip is not None:
        sims[skip] = -1
    by = defaultdict(list)
    for s, c in zip(sims, exemplar_class):
        by[c].append(float(s))
    score = {c: float(np.mean(sorted(x, reverse=True)[:3])) for c, x in by.items()}
    return max(s for c, s in score.items() if c != 'search') - score['search']


def fitted_gates():
    """Thresholds from leave-one-out on the exemplars only, never on the queries."""
    labels = [c != 'search' for c in exemplar_class]
    margins = [class_margin(exemplar_vectors[i], i) for i in range(len(labels))]
    texts = meta['exemplar_texts']
    research = [nli[t]['research'] for t in texts]

    def balanced(flags):
        pos = [f for f, y in zip(flags, labels) if y]
        neg = [f for f, y in zip(flags, labels) if not y]
        return (sum(pos) / len(pos) + (len(neg) - sum(neg)) / len(neg)) / 2
    margin = max(np.arange(-0.15, 0.15, 0.005), key=lambda t: balanced([m > t for m in margins]))
    tau = max(np.arange(0.05, 0.95, 0.01), key=lambda t: balanced([r < t for r in research]))
    return {'margin': float(margin), 'margin_loo_bacc': balanced([m > margin for m in margins]), 'tau': float(tau), 'tau_bacc': balanced([r < tau for r in research])}


GATES = fitted_gates()


def refused(text, parsed, cfg):
    if parsed['intent'] != 'search':
        return True
    if AVOID_ONLY.search(text) and not POSITIVE.search(text):
        return True
    if cfg.get('gate') == 'E' and parsed['dislikes']:  # a stated dislike pulls towards 'only_dislike' even when a like is given
        return False
    if cfg.get('gate') == 'E':
        return class_margin(query_vector[text]) > GATES['margin']
    if cfg.get('gate') == 'N':
        return nli[text]['research'] < GATES['tau']
    return False


def rank(text, cfg):
    """Top 10 labs for a config, or None when the input is refused. Unknown keys mean the component is off."""
    parsed, positive = cached(memo_forms, text, lambda: forms(text))
    if refused(text, parsed, cfg):
        return None
    likes, dislikes = parsed['likes'] or [text], parsed['dislikes']
    english = translations.get(positive) or ''
    extended = f'{positive} {english}' if english else positive
    query = extended if cfg.get('T') else positive
    penalties = [cached(memo_dense, (d, 0, 0), lambda: aggregate(V @ query_vector[d], index)) for d in dislikes]
    allowed = lambda l: not engine.conflicts_with_dislikes(l, dislikes)
    probe = extended if cfg.get('TD') else ' '.join(likes)
    cards = cached(memo_search, probe, lambda: catalog.search(probe))
    lists = [[c['id'] for c in cards if allowed(c['id'])]]
    if cfg.get('doc', True) and all(p in doc_table for p in likes + dislikes + [parsed['norm']]):
        plan = {'likes': likes, 'dislikes': dislikes, 'norm': parsed['norm']}
        lists.append(engine.embedding_ranking(plan, {p: doc_table[p] for p in dict.fromkeys(likes + dislikes + [parsed['norm']])})[0])
    v = expanded(query_vector[query], cfg)
    lists.append(ranked(cached(memo_dense, (query, cfg.get('C', 0), cfg.get('P', 0)), lambda: aggregate(V @ v, index)), penalties))
    if cfg.get('S'):
        lists.append(ranked(as_labs(lexical['sparse'][query]), penalties))
    if cfg.get('B'):
        lists.append(ranked(as_labs(lexical['colbert'][query]), penalties))
    if cfg.get('R'):
        lists.append(ranked(as_labs(reranks['scores'][query]), penalties))
    if cfg.get('Q'):
        lists.append(ranked(aggregate(d2q_vectors @ v, {o: np.array(d2q_index[o], dtype=int) for o in known}), penalties))
        lists.append(ranked(as_labs(lexical['sparse_d2q'][query]), penalties))
    cue = bool(COURSE_CUE.search(text))
    links, every = cached(memo_links, (tuple(likes), cue), lambda: (catalog.course_labs(catalog.courses_named(likes, cue)), all(catalog.courses_named([x], cue) for x in likes)))
    linked = {l: x for l, x in links.items() if allowed(l)}
    led = bool(linked) and (cue or every)
    return [l for l in CuratedQueryEngine.fuse(linked, led, *[x for x in lists if x]) if allowed(l)][:10]


def sonnet_rank(text, parse):
    """A5, the comparison baseline: Sonnet's intent, split and search text over the same dictionary, chunks and course links."""
    if parse['intent'] != 'search':
        return None
    likes, dislikes, search = parse['likes'] or [parse['search_text']], parse['dislikes'], parse['search_text']
    allowed = lambda l: not engine.conflicts_with_dislikes(l, dislikes)
    lists = [[c['id'] for c in catalog.search(search) if allowed(c['id'])]]
    lists.append(ranked(aggregate(V @ query_vector[search], index), [aggregate(V @ query_vector[d], index) for d in dislikes]))
    cue = bool(COURSE_CUE.search(text))
    linked = {l: x for l, x in catalog.course_labs(catalog.courses_named(likes, cue)).items() if allowed(l)}
    led = bool(linked) and (cue or all(catalog.courses_named([x], cue) for x in likes))
    return [l for l in CuratedQueryEngine.fuse(linked, led, *[x for x in lists if x]) if allowed(l)][:10]


class Replay:
    def request(self, phrases, timeout, remote=True):
        return {p: doc_table[p] for p in phrases} if all(p in doc_table for p in phrases) else None


current_engine = CuratedQueryEngine(catalog, Replay())


def current(text):
    found = current_engine.search(text)
    return [c['id'] for c in found['labs']][:10] if found['intent'] == 'search' else None


dcg = lambda g: sum(x / math.log2(i + 2) for i, x in enumerate(g))
mean = lambda v: sum(v) / len(v) if v else 0.0
SCHEMA = pj.SCHEMA


def ask(prompt, key, path):
    if path.exists() and json.loads(path.read_text()).get('ok'):
        return json.loads(path.read_text())
    cmd = ['claude', '-p', '--model', 'sonnet', '--effort', 'medium', '--tools', '', '--no-session-persistence', '--system-prompt', pj.SYSTEM, '--output-format', 'json', '--json-schema', json.dumps(SCHEMA, separators=(',', ':'))]
    try:
        d = json.loads(subprocess.run(cmd, input=prompt, text=True, capture_output=True, cwd='/tmp', timeout=300).stdout)
        v = d.get('structured_output')
        r = {'ok': isinstance(v, dict) and {g['label'] for g in v['grades']} == set(key), 'value': v, 'key': key, 'cost': d.get('total_cost_usd')}
    except Exception as exc:
        r = {'ok': False, 'key': key, 'error': f'{type(exc).__name__}: {exc}'[:300]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(r, ensure_ascii=False))
    return r


# ---- dev set ----
OPTIONS = [('T', {'T': 1}), ('TD', {'TD': 1}), ('C.3', {'C': .3}), ('C.6', {'C': .6}), ('P.3', {'P': .3}), ('P.6', {'P': .6}),
           ('S', {'S': 1}), ('B', {'B': 1}), ('R', {'R': 1}), ('nodoc', {'doc': False}), ('gateE', {'gate': 'E'}), ('gateN', {'gate': 'N'})]
EXCLUSIVE = [{'C.3', 'C.6'}, {'P.3', 'P.6'}, {'gateE', 'gateN'}]
MIN_GAIN = 0.005


def dev_scores(results, gain, should, controls, queries):
    out = {}
    for q in queries:
        k, top = q['id'], (results[q['id']] or [])[:5]
        if should[k]:
            ideal = dcg(sorted((v for l, v in gain[k].items() if l not in controls[k]), reverse=True)[:5]) or 1
            out[k] = dcg([gain[k].get(l, 0) for l in top]) / ideal
        else:
            out[k] = 1.0 if not top else 0.0
    return out


def greedy(queries, gain, should, controls, start, options, cache):
    def fit(names):
        key = tuple(sorted(names))
        if key not in cache:
            cfg = dict(start)
            for n, part in options_map.items():
                if n in names:
                    cfg.update(part)
            cache[key] = {q['id']: rank(q['text'], cfg) for q in queries}
        s = dev_scores(cache[key], gain, should, controls, queries)
        return mean(list(s.values()))
    options_map = dict(options)
    chosen, best, path = [], fit([]), []
    path.append(('base', round(best, 3)))
    while True:
        blocked = {x for group in EXCLUSIVE if group & set(chosen) for x in group}
        trials = {n: fit(chosen + [n]) for n in options_map if n not in chosen and n not in blocked}
        if not trials:
            break
        name = max(trials, key=trials.get)
        if trials[name] - best < MIN_GAIN:
            break
        chosen.append(name)
        best = trials[name]
        path.append((name, round(best, 3), {k: round(v, 3) for k, v in sorted(trials.items(), key=lambda kv: -kv[1])}))
    return chosen, best, path


def config(names, base):
    cfg = dict(base)
    for n, part in OPTIONS + [('Q', {'Q': 1})]:
        if n in names:
            cfg.update(part)
    return cfg


def judge_new(queries, gain, should, controls, wanted, tag):
    """Grade unjudged (query, lab) pairs with the panel, next to six labs already graded for that query."""
    todo = []
    for q in queries:
        k = q['id']
        fresh = sorted({l for l in wanted.get(k, ()) if l not in gain[k]})
        if not fresh or not should[k]:
            continue
        anchors = [l for _, l in sorted(((v, l) for l, v in gain[k].items()), reverse=True)[::max(1, len(gain[k]) // 6)]][:6]
        cards = {l: pj.card_text(catalog, papers, l) for l in fresh + anchors}
        for j in range(1, 6):
            order = fresh + anchors
            random.Random(f'{tag}-{k}-{j}').shuffle(order)
            key = {f'L{i + 1}': l for i, l in enumerate(order)}
            body = '\n'.join(f'[{a}] ' + json.dumps(cards[l], ensure_ascii=False) for a, l in key.items())
            todo.append((k, fresh, key, f"{pj.RULES}\n\n학생 입력: {q['text']}\n\n연구실 카드:\n{body}", HERE / 'dev_calls' / f'{tag}_{k}_j{j}.json'))
    print(tag, 'judge calls', len(todo), 'pairs', sum(len(t[1]) for t in todo) // 5, flush=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda t: ask(t[3], t[2], t[4]), todo))
    extra = defaultdict(lambda: defaultdict(list))
    for t, r in zip(todo, results):
        if r['ok']:
            for g in r['value']['grades']:
                if r['key'][g['label']] in t[1]:
                    extra[t[0]][r['key'][g['label']]].append(g['grade'])
            (HERE / 'dev_extra.jsonl').open('a').write(json.dumps({'q': t[0], 'fresh': t[1], 'key': r['key'], 'grades': r['value']['grades']}, ensure_ascii=False) + '\n')
    for k, labs in extra.items():
        gain[k].update({l: mean(v) for l, v in labs.items()})
    print('cost', round(sum(r.get('cost') or 0 for r in results), 2), 'failed', sum(not r['ok'] for r in results), flush=True)


def load_extra(gain):
    path = HERE / 'dev_extra.jsonl'
    pooled = defaultdict(lambda: defaultdict(list))
    if path.exists():
        for row in map(json.loads, path.read_text().splitlines()):
            for g in row['grades']:
                if row['key'][g['label']] in row['fresh']:
                    pooled[row['q']][row['key'][g['label']]].append(g['grade'])
    for k, labs in pooled.items():
        gain[k].update({l: mean(v) for l, v in labs.items()})


def select():
    queries, gain, should, controls = grades.load()
    load_extra(gain)
    print('gates', GATES, flush=True)
    base = {}
    for round_no in range(1, 4):
        cache = {}
        chosen, best, path = greedy(queries, gain, should, controls, base, OPTIONS, cache)
        cfg1 = config(chosen, base)
        n2_opts = OPTIONS + [('Q', {'Q': 1})]
        trial = {q['id']: rank(q['text'], {**cfg1, 'Q': HAS_Q}) for q in queries}
        wanted = defaultdict(set)
        for key, results in cache.items():  # the chosen path and every single-component addition
            if len(key) <= 1 or set(key) <= set(chosen):
                for k, r in results.items():
                    wanted[k] |= set((r or [])[:5])
        for k, r in trial.items():
            wanted[k] |= set((r or [])[:5])
        missing = sum(l not in gain[k] for k in wanted for l in wanted[k] if should[k])
        print(f'round {round_no}: chosen {chosen} fit {best:.3f}; unjudged pairs {missing}', flush=True)
        if missing == 0:
            break
        judge_new(queries, gain, should, controls, wanted, f'r{round_no}')
    cache = {}
    chosen, best, path = greedy(queries, gain, should, controls, base, OPTIONS, cache)
    cfg1 = config(chosen, base)
    base_scores = dev_scores({q['id']: rank(q['text'], cfg1) for q in queries}, gain, should, controls, queries)
    with_q = dev_scores({q['id']: rank(q['text'], {**cfg1, 'Q': HAS_Q}) for q in queries}, gain, should, controls, queries)
    q_gain = mean(list(with_q.values())) - mean(list(base_scores.values()))
    frozen = {'N1': cfg1, 'N2': {**cfg1, 'Q': 1}, 'N1_names': chosen, 'gates': GATES, 'path': path, 'dev_fit_N1': round(mean(list(base_scores.values())), 3),
              'dev_fit_N2': round(mean(list(with_q.values())), 3), 'q_gain': round(q_gain, 3)}
    (HERE / 'frozen.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=1))
    llm = json.loads((grades.BASE / 'llm_parse.json').read_text())
    a4 = dev_scores({q['id']: rank(q['text'], {}) for q in queries}, gain, should, controls, queries)
    a5 = dev_scores({q['id']: sonnet_rank(q['text'], llm[q['id']]) for q in queries}, gain, should, controls, queries)
    print(json.dumps({k: v for k, v in frozen.items() if k != 'path'}, ensure_ascii=False))
    print('path', *path, sep='\n  ')
    print('dev fit A4 (base)', round(mean(list(a4.values())), 3), 'A5', round(mean(list(a5.values())), 3))


# ---- test set ----
def test_rankings():
    frozen = json.loads((HERE / 'frozen.json').read_text())
    queries = json.loads((HERE / 'holdout.json').read_text())
    llm = json.loads((HERE / 'llm_parse_holdout.json').read_text())
    return queries, {'A0': {q['id']: current(q['text']) for q in queries}, 'A4': {q['id']: rank(q['text'], {}) for q in queries},
                     'A5': {q['id']: sonnet_rank(q['text'], llm[q['id']]) for q in queries},
                     'N1': {q['id']: rank(q['text'], frozen['N1']) for q in queries}, 'N2': {q['id']: rank(q['text'], frozen['N2']) for q in queries}}


def test():
    queries, R = test_rankings()
    (HERE / 'test_rankings.json').write_text(json.dumps(R, ensure_ascii=False, indent=1))
    labs = sorted(catalog.profiles)
    todo, pools = [], {}
    for q in queries:
        k = q['id']
        pool = list(dict.fromkeys(l for s in R for l in (R[s][k] or [])[:5]))
        depts = {catalog.profiles[l]['department'] for l in pool}
        outside = [l for l in labs if l not in pool]
        controls = random.Random(f'ctrl-{k}').sample([l for l in outside if catalog.profiles[l]['department'] not in depts] or outside, 2)
        pools[k] = {'labs': pool, 'controls': controls}
        cards = {l: pj.card_text(catalog, papers, l) for l in pool + controls}
        for j in range(1, 6):
            order = pool + controls
            random.Random(f'{k}-{j}').shuffle(order)
            key = {f'L{i + 1}': l for i, l in enumerate(order)}
            body = '\n'.join(f'[{a}] ' + json.dumps(cards[l], ensure_ascii=False) for a, l in key.items())
            todo.append((key, f"{pj.RULES}\n\n학생 입력: {q['text']}\n\n연구실 카드:\n{body}", HERE / 'test_calls' / f'{k}_j{j}.json'))
    (HERE / 'test_pools.json').write_text(json.dumps(pools, ensure_ascii=False, indent=1))
    print('calls', len(todo), flush=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda t: ask(t[1], t[0], t[2]), todo))
    print('ok', sum(r['ok'] for r in results), '/', len(results), 'cost', round(sum(r.get('cost') or 0 for r in results), 2))


def boot(d, reps=10000, seed=23):
    rng = random.Random(seed)
    ms = sorted(mean([rng.choice(d) for _ in d]) for _ in range(reps))
    return [round(ms[int(.025 * reps)], 3), round(ms[int(.975 * reps) - 1], 3)]


def analyze():
    queries = json.loads((HERE / 'holdout.json').read_text())
    R = json.loads((HERE / 'test_rankings.json').read_text())
    pools = json.loads((HERE / 'test_pools.json').read_text())
    grades_, votes = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    failed = 0
    for q in queries:
        for j in range(1, 6):
            r = json.loads((HERE / 'test_calls' / f"{q['id']}_j{j}.json").read_text())
            if not r.get('ok'):
                failed += 1
                continue
            votes[q['id']].append(r['value']['should_recommend'])
            for g in r['value']['grades']:
                grades_[q['id']][r['key'][g['label']]].append(g['grade'])
    gain = {k: {l: mean(v) for l, v in x.items()} for k, x in grades_.items()}
    should = {k: sum(v) > len(v) / 2 for k, v in votes.items()}
    controls = {k: v['controls'] for k, v in pools.items()}
    scores = {s: dev_scores(R[s], gain, should, controls, queries) for s in R}
    rec = [q['id'] for q in queries if should[q['id']]]
    refuse = [q['id'] for q in queries if not should[q['id']]]
    ids = [q['id'] for q in queries]
    table = {s: {'fit': round(mean([scores[s][k] for k in ids]), 3), 'ndcg5_recommend': round(mean([scores[s][k] for k in rec]), 3),
                 'correct_refusal': sum(scores[s][k] == 1.0 for k in refuse), 'wrong_refusal': sum(not R[s][k] for k in rec)} for s in R}
    compare = {f'{a}-{b}': {'diff': round(mean([scores[a][k] - scores[b][k] for k in ids]), 3), 'ci95': boot([scores[a][k] - scores[b][k] for k in ids]),
                            'recommend_only': round(mean([scores[a][k] - scores[b][k] for k in rec]), 3), 'recommend_only_ci95': boot([scores[a][k] - scores[b][k] for k in rec])}
               for a, b in [('N1', 'A5'), ('N2', 'A5'), ('N1', 'A4'), ('N2', 'A4'), ('N1', 'A0'), ('N2', 'N1'), ('A5', 'A4'), ('A5', 'A0')]}
    types = defaultdict(list)
    for q in queries:
        types[q['type']].append(q['id'])
    by_type = {t: {s: round(mean([scores[s][k] for k in qs]), 3) for s in R} for t, qs in types.items()}
    judged = [g for k, labs in gain.items() for l, g in labs.items() if l in controls[k]]
    pooled = [g for k, labs in gain.items() for l, g in labs.items() if l not in controls[k]]
    wrong = {s: {'wrong_refusals': [k for k in rec if not R[s][k]], 'missed_refusals': [k for k in refuse if R[s][k]]} for s in R}
    metrics = {'table': table, 'compare': compare, 'by_type': by_type, 'n_recommend': len(rec), 'n_refuse': len(refuse), 'failed_calls': failed, 'control_mean': round(mean(judged), 3), 'pool_mean': round(mean(pooled), 3),
               'errors': wrong, 'per_query': {k: {s: round(scores[s][k], 3) for s in R} for k in ids}}
    (HERE / 'test_metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in metrics.items() if k != 'per_query'}, ensure_ascii=False, indent=1))


{'select': select, 'test': test, 'analyze': analyze}[command]()
