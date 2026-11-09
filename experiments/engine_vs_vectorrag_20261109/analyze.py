"""Panel metrics (nDCG@10, P@5, MRR, junk@5), reliability, controls, and gold-label metrics. Writes metrics.json."""
import json
import math
import random
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
queries = json.loads((OUT / 'queries.json').read_text())
rankings = json.loads((OUT / 'rankings.json').read_text())
pools = json.loads((OUT / 'pools.json').read_text())
ENGINES = ('H', 'V')
mean = lambda xs: sum(xs) / len(xs) if xs else None


def load_grades():
    grades, failures = defaultdict(lambda: defaultdict(list)), []
    for q in queries:
        if not q['panel']:
            continue
        for j in range(1, 6):
            path = OUT / 'calls' / f"{q['id']}_j{j}.json"
            r = json.loads(path.read_text()) if path.exists() else {'ok': False}
            if not r.get('ok'):
                failures.append(f"{q['id']}_j{j}")
                continue
            for g in r['value']['grades']:
                grades[q['id']][r['key'][g['label']]].append(g['grade'])
    return grades, failures


def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg(ranked, gain, k=10):
    ideal = dcg(sorted(gain.values(), reverse=True)[:k])
    return dcg([gain.get(l, 0.0) for l in ranked[:k]]) / ideal if ideal else 0.0


def per_query(ranked, gain):
    top5 = [gain.get(l, 0.0) for l in ranked[:5]]
    rr = next((1 / (i + 1) for i, l in enumerate(ranked[:10]) if gain.get(l, 0.0) >= 2), 0.0)
    return {'ndcg10': ndcg(ranked, gain), 'p5': sum(g >= 2 for g in top5) / 5, 'mrr': rr, 'junk5': sum(g < 1 for g in top5) / 5,
            'n_returned': len(ranked)}


def bootstrap(diffs, reps=10000, seed=11):
    rng = random.Random(seed)
    means = sorted(mean([rng.choice(diffs) for _ in diffs]) for _ in range(reps))
    return [round(means[int(.025 * reps)], 3), round(means[int(.975 * reps) - 1], 3)]


def alpha(units):
    """Krippendorff's alpha, interval metric."""
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    do = sum(sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j) / (len(u) - 1) for u in units) / n
    values = [v for u in units for v in u]
    count = defaultdict(int)
    for v in values:
        count[v] += 1
    de = sum(count[a] * count[b] * (a - b) ** 2 for a in count for b in count) / (n * (n - 1))
    return 1 - do / de


def summarise(rows):
    out = {e: {m: round(mean([r[e][m] for r in rows]), 3) for m in rows[0][e]} for e in ENGINES}
    diffs = [r['H']['ndcg10'] - r['V']['ndcg10'] for r in rows]
    out['ndcg10_diff_H_minus_V'] = round(mean(diffs), 3)
    out['ndcg10_diff_ci95'] = bootstrap(diffs)
    out['wins'] = {'H': sum(d > 0.005 for d in diffs), 'V': sum(d < -0.005 for d in diffs), 'tie': sum(abs(d) <= 0.005 for d in diffs)}
    out['n'] = len(rows)
    return out


def main():
    grades, failures = load_grades()
    gain = {qid: {l: mean(v) for l, v in labs.items()} for qid, labs in grades.items()}
    rows = {}
    for q in queries:
        if q['panel'] and q['id'] in gain:
            pool_gain = {l: g for l, g in gain[q['id']].items() if l not in pools[q['id']]['controls']}
            rows[q['id']] = {e: per_query(rankings[e][q['id']]['labs'], pool_gain) for e in ENGINES}
    groups = defaultdict(list)
    for q in queries:
        if q['id'] in rows:
            groups['ALL'].append(rows[q['id']])
            groups[q['group']].append(rows[q['id']])
            if q.get('type'):
                groups['B:' + q['type']].append(rows[q['id']])
    metrics = {'panel': {g: summarise(v) for g, v in groups.items()}, 'failures': failures}
    all_units = [v for labs in grades.values() for v in labs.values()]
    metrics['alpha_all'] = round(alpha(all_units), 3)
    control = [g for qid, labs in gain.items() for l, g in labs.items() if l in pools[qid]['controls']]
    pooled = [g for qid, labs in gain.items() for l, g in labs.items() if l not in pools[qid]['controls']]
    metrics['control_mean_grade'], metrics['pool_mean_grade'] = round(mean(control), 3), round(mean(pooled), 3)
    metrics['control_above_1'] = round(sum(g >= 1 for g in control) / len(control), 3)

    # Gold labels from the teammate's evaluation set: professor-level ranks.
    gold = []
    for q in queries:
        if q['group'] != 'T':
            continue
        rel = set(q['relevant'])
        row = {}
        for name, ranked in (('H', rankings['H'][q['id']]['labs']), ('V', rankings['V_professor_rank'][q['id']])):
            hits = [i + 1 for i, l in enumerate(ranked) if l in rel]
            row[name] = {'hit1': int(bool(hits and hits[0] == 1)), 'hit5': int(bool(hits and hits[0] <= 5)), 'mrr': 1 / hits[0] if hits else 0.0,
                         'recall5': sum(h <= 5 for h in hits) / len(rel)}
        gold.append(row)
    metrics['gold_T30'] = {e: {m: round(mean([r[e][m] for r in gold]), 3) for m in gold[0][e]} for e in ENGINES}
    h_top, v_top = rankings['H'], rankings['V']
    metrics['overlap_top10_mean'] = round(mean([len(set(h_top[q['id']]['labs']) & set(v_top[q['id']]['labs'])) for q in queries]), 2)
    metrics['timing'] = rankings['timing']
    per = {q['id']: {'group': q['group'], 'text': q['text'], **{e: round(rows[q['id']][e]['ndcg10'], 3) for e in ENGINES}} for q in queries if q['id'] in rows}
    metrics['per_query'] = per
    (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in metrics.items() if k != 'per_query'}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
