"""Automatic checks, professor-panel aggregation, judge reliability and lab-level bootstrap. Writes metrics.json.

Run: PYTHONPATH=. python3 experiments/research_persona_20261107/analyze.py
"""
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

from curri.curated_catalog import content_words

OUT = Path(__file__).resolve().parent
cases = json.loads((OUT / 'cases.json').read_text())
pool = {lid: words for lid, words in json.loads((OUT / 'future_pool.json').read_text()).items()}
CRITERIA = ['doable', 'lab_fit', 'course_fit', 'interest_fit', 'grounded', 'useful', 'next_courses']
METHODS = ['A', 'L', 'R', 'RS', 'RSO']
LLM = ['L', 'R', 'RS', 'RSO']


def load(stage, name):
    path = OUT / 'calls' / stage / f'{name}.json'
    return json.loads(path.read_text()) if path.exists() else None


def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip().lower()


def source_texts(case, method):
    texts = {s['id']: s['text'] for s in case['profile_sources']}
    if method == 'R':
        texts.update({p['id']: p['title'] + ' ' + p['abstract'] for p in case['papers']})
    if method in ('RS', 'RSO'):
        texts.update({s['paper']['id']: s['paper']['title'] + ' ' + s['paper']['abstract'] for s in case['rs_selection']})
    if method == 'RSO':
        texts.update({f'C{i + 1}': p['title'] + ' ' + p['abstract'] for i, p in enumerate(case['openalex_citing'])})
    return texts


def automatic(case, method, value):
    texts = source_texts(case, method)
    taken = {c['code'] for c in case['transcript']}
    allowed = {c['code'] for c in case['candidate_courses']}
    quotes = [t['lab_basis'] for t in value['topics']]
    quote_ok = [q['source_id'] in texts and norm(q['quote']) in norm(texts[q['source_id']]) and len(norm(q['quote'])) >= 8 for q in quotes]
    course_refs = [cb['course_code'] for t in value['topics'] for cb in t['course_basis']]
    next_refs = [n['course_code'] for n in value['next_courses']]
    paper_quote = [q['source_id'][:1] in 'PC' for q in quotes]
    return {'quote_ok': quote_ok, 'course_ref_ok': [c in taken for c in course_refs],
            'next_ok': [c in allowed for c in next_refs], 'paper_grounded': paper_quote,
            'course_links': len(course_refs)}


def tfidf(words, idf):
    counts = defaultdict(int)
    for w in words:
        counts[w] += 1
    vec = {w: c * idf.get(w, 0.0) for w, c in counts.items()}
    size = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {w: v / size for w, v in vec.items()}


def time_split(outputs):
    """Rank of the case's own lab among all pool labs by similarity of the output keywords to their 2025+ papers."""
    docs = {lid: set(words) for lid, words in pool.items()}
    idf = {w: math.log((len(docs) + 1) / (sum(w in d for d in docs.values()) + 1)) for w in set().union(*docs.values())}
    lab_vecs = {lid: tfidf(words, idf) for lid, words in pool.items()}
    result = {}
    for (case_id, method), words in outputs.items():
        lid = next(c['lab_id'] for c in cases if c['id'] == case_id)
        q = tfidf(words, idf)
        sims = sorted(((sum(v * lab_vecs[l].get(w, 0.0) for w, v in q.items()), l) for l in lab_vecs), reverse=True)
        rank = next(i for i, (_, l) in enumerate(sims, 1) if l == lid)
        result[(case_id, method)] = rank
    return result


def alpha_interval(units):
    """Krippendorff's alpha for interval data. units: list of lists of ratings (one list per item)."""
    pairable = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in pairable)
    if n < 2:
        return None
    do = sum(sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j) / (len(u) - 1) for u in pairable) / n
    values = [v for u in pairable for v in u]
    de = sum((a - b) ** 2 for i, a in enumerate(values) for j, b in enumerate(values) if i != j) / (n * (n - 1))
    return None if de == 0 else 1 - do / de


def bootstrap_diff(per_lab_a, per_lab_b, reps=4000, seed=7):
    labs = sorted(per_lab_a)
    diffs = []
    rng = random.Random(seed)
    for _ in range(reps):
        sample = [rng.choice(labs) for _ in labs]
        diffs.append(sum(per_lab_a[l] - per_lab_b[l] for l in sample) / len(sample))
    diffs.sort()
    point = sum(per_lab_a[l] - per_lab_b[l] for l in labs) / len(labs)
    return round(point, 3), [round(diffs[int(0.025 * reps)], 3), round(diffs[int(0.975 * reps) - 1], 3)]


def main():
    metrics = {'auto': {}, 'panel': {}, 'reliability': {}, 'sensitivity': {}, 'time_split': {}, 'cost': {}, 'failures': []}
    outputs, auto_rows = {}, defaultdict(lambda: defaultdict(list))
    for c in cases:
        guide = c['baseline_guide']
        outputs[(c['id'], 'A')] = [w for t in guide['start_now'][:2] for w in content_words(t['evidence'][0]['title'] if t['evidence'] else t['title'])]
        for m in LLM:
            r = load('generate', f'{m}_{c["id"]}')
            if not r or not r.get('ok'):
                metrics['failures'].append(f'generate {m}_{c["id"]}')
                continue
            v = r['value']
            outputs[(c['id'], m)] = [w for k in v['keywords_en'] for w in content_words(k)]
            a = automatic(c, m, v)
            for k in ('quote_ok', 'course_ref_ok', 'next_ok', 'paper_grounded'):
                auto_rows[m][k] += a[k]
            auto_rows[m]['course_links'].append(a['course_links'])
            auto_rows[m]['seconds'].append(r['duration_wall_s'])
            auto_rows[m]['cost'].append(r.get('cost_usd_list') or 0)
    for m, rows in auto_rows.items():
        metrics['auto'][m] = {k: round(sum(v) / len(v), 3) for k, v in rows.items() if v and k not in ('seconds', 'cost')}
        metrics['cost'][m] = {'calls_per_case': 1, 'mean_seconds': round(sum(rows['seconds']) / len(rows['seconds']), 1),
                              'mean_cost_usd_list': round(sum(rows['cost']) / len(rows['cost']), 4)}
    ranks = time_split(outputs)
    for m in METHODS:
        rs = [ranks[(c['id'], m)] for c in cases if (c['id'], m) in ranks]
        if rs:
            metrics['time_split'][m] = {'mrr': round(sum(1 / r for r in rs) / len(rs), 3), 'hit1': round(sum(r == 1 for r in rs) / len(rs), 3),
                                        'hit10': round(sum(r <= 10 for r in rs) / len(rs), 3), 'median_rank': sorted(rs)[len(rs) // 2],
                                        'pool_size': len(pool)}
    keys = json.loads((OUT / 'judge_keys.json').read_text()) if (OUT / 'judge_keys.json').exists() else {}
    scores = defaultdict(lambda: defaultdict(list))   # (case, method) -> criterion -> [judge scores]
    for name, key in keys.items():
        r = load('judge', name)
        if not r or not r.get('ok'):
            metrics['failures'].append(f'judge {name}')
            continue
        case_id = name.rsplit('_j', 1)[0]
        evals = {e['label']: e for e in r['value']['evaluations']}
        if set(evals) != set(key):
            metrics['failures'].append(f'judge {name}: labels {sorted(evals)}')
            continue
        for label, method in key.items():
            e = evals[label]
            for k in CRITERIA:
                scores[(case_id, method)][k].append(e[k])
            scores[(case_id, method)]['composite'].append(sum(e[k] for k in CRITERIA) / len(CRITERIA))
            scores[(case_id, method)]['accept'].append(1.0 if e['accept'] else 0.0)
            scores[(case_id, method)]['rank'].append(e['rank'])
    if scores:
        fields = CRITERIA + ['composite', 'accept', 'rank']
        mean = lambda xs: sum(xs) / len(xs)
        case_mean = {(cid, m): {k: mean(v) for k, v in d.items()} for (cid, m), d in scores.items()}
        for m in METHODS + ['CTRL']:
            rows = [case_mean[(c['id'], m)] for c in cases if (c['id'], m) in case_mean]
            metrics['panel'][m] = {k: round(mean([r[k] for r in rows]), 3) for k in fields}
            for cond in ('fit', 'misfit'):
                rows_c = [case_mean[(c['id'], m)] for c in cases if c['condition'] == cond and (c['id'], m) in case_mean]
                metrics['panel'][m][cond] = {k: round(mean([r[k] for r in rows_c]), 3) for k in ('composite', 'doable', 'course_fit', 'accept')}
        for k in CRITERIA + ['composite']:
            metrics['reliability'][k] = round(alpha_interval([d[k] for d in scores.values()]) or float('nan'), 3)
        labs = sorted({c['professor'] for c in cases})
        per_lab = {m: {l: mean([case_mean[(c['id'], m)]['composite'] for c in cases if c['professor'] == l]) for l in labs} for m in METHODS}
        best = max(METHODS, key=lambda m: metrics['panel'][m]['composite'])
        metrics['best_by_composite'] = best
        metrics['pairwise_vs_best'] = {m: bootstrap_diff(per_lab[best], per_lab[m]) for m in METHODS if m != best}
        metrics['pairwise_vs_A'] = {m: bootstrap_diff(per_lab[m], per_lab['A']) for m in METHODS if m != 'A'}
        for m in METHODS:
            diffs = {k: [case_mean[(f'{l}_fit', m)][k] - case_mean[(f'{l}_misfit', m)][k] for l in labs] for k in ('course_fit', 'doable')}
            metrics['sensitivity'][m] = {k: round(mean(v), 3) for k, v in diffs.items()}
    (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1))
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
