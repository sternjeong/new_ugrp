"""Fit score per strategy (nDCG@5 where a recommendation is right, correct refusal otherwise), secondary metrics, bootstrap."""
import json
import math
import random
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
queries = json.loads((OUT / 'queries.json').read_text())
rankings = json.loads((OUT / 'rankings.json').read_text())
pools = json.loads((OUT / 'pools.json').read_text())
R = rankings['rankings']
NAMES = list(R)
mean = lambda xs: sum(xs) / len(xs) if xs else None


def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def alpha(units):
    units = [u for u in units if len(u) >= 2]
    n = sum(len(u) for u in units)
    do = sum(sum((a - b) ** 2 for i, a in enumerate(u) for j, b in enumerate(u) if i != j) / (len(u) - 1) for u in units) / n
    count = defaultdict(int)
    for u in units:
        for v in u:
            count[v] += 1
    de = sum(count[a] * count[b] * (a - b) ** 2 for a in count for b in count) / (n * (n - 1))
    return 1 - do / de


def bootstrap(diffs, reps=10000, seed=13):
    rng = random.Random(seed)
    means = sorted(mean([rng.choice(diffs) for _ in diffs]) for _ in range(reps))
    return [round(means[int(.025 * reps)], 3), round(means[int(.975 * reps) - 1], 3)]


def main():
    grades, votes, failures, cost = defaultdict(lambda: defaultdict(list)), defaultdict(list), [], 0.0
    for q in queries:
        for j in range(1, 6):
            path = OUT / 'calls' / f"{q['id']}_j{j}.json"
            r = json.loads(path.read_text()) if path.exists() else {'ok': False}
            if not r.get('ok'):
                failures.append(f"{q['id']}_j{j}")
                continue
            cost += r.get('cost_usd_list') or 0
            votes[q['id']].append(bool(r['value']['should_recommend']))
            for g in r['value']['grades']:
                grades[q['id']][r['key'][g['label']]].append(g['grade'])
    gain = {qid: {l: mean(v) for l, v in labs.items()} for qid, labs in grades.items()}
    should = {qid: sum(v) > len(v) / 2 for qid, v in votes.items()}
    scores, details = defaultdict(dict), defaultdict(dict)
    for q in queries:
        qid = q['id']
        pool_gain = {l: g for l, g in gain[qid].items() if l not in pools[qid]['controls']}
        ideal = dcg(sorted(pool_gain.values(), reverse=True)[:5]) or 1.0
        for name in NAMES:
            ranked = (R[name][qid] or [])[:5]
            if should[qid]:
                nd = dcg([gain[qid].get(l, 0.0) for l in ranked]) / ideal if ranked else 0.0
                scores[name][qid] = nd
                details[name][qid] = {'ndcg5': nd, 'p5': sum(gain[qid].get(l, 0) >= 2 for l in ranked) / 5, 'junk5': sum(gain[qid].get(l, 0) < 1 for l in ranked) / 5 if ranked else None, 'answered': bool(ranked)}
            else:
                scores[name][qid] = 1.0 if not ranked else 0.0
    rec_q = [q['id'] for q in queries if should[q['id']]]
    no_q = [q['id'] for q in queries if not should[q['id']]]
    table = {}
    for name in NAMES:
        table[name] = {'fit': round(mean(list(scores[name].values())), 3), 'ndcg5_recommend': round(mean([details[name][q]['ndcg5'] for q in rec_q]), 3),
                       'p5_recommend': round(mean([details[name][q]['p5'] for q in rec_q]), 3),
                       'junk5_recommend': round(mean([details[name][q]['junk5'] for q in rec_q if details[name][q]['junk5'] is not None]), 3),
                       'answered_recommend': sum(details[name][q]['answered'] for q in rec_q), 'correct_refusal': sum(scores[name][q] == 1.0 for q in no_q)}
    best = max(NAMES, key=lambda n: table[n]['fit'])
    ids = [q['id'] for q in queries]
    vs = {'vs_A0': {n: {'diff': round(mean([scores[n][i] - scores['A0'][i] for i in ids]), 3), 'ci95': bootstrap([scores[n][i] - scores['A0'][i] for i in ids])} for n in NAMES if n != 'A0'},
          'vs_best': {n: {'diff': round(mean([scores[best][i] - scores[n][i] for i in ids]), 3), 'ci95': bootstrap([scores[best][i] - scores[n][i] for i in ids])} for n in NAMES if n != best}}
    types = defaultdict(list)
    for q in queries:
        types[q['type']].append(q['id'])
    by_type = {t: {n: round(mean([scores[n][i] for i in qs]), 3) for n in NAMES} for t, qs in types.items()}
    control = [g for qid, labs in gain.items() for l, g in labs.items() if l in pools[qid]['controls']]
    pooled = [g for qid, labs in gain.items() for l, g in labs.items() if l not in pools[qid]['controls']]
    metrics = {'table': table, 'best': best, **vs, 'by_type': by_type, 'should_recommend': should, 'should_votes': {k: sum(v) for k, v in votes.items()},
               'n_should_recommend': len(rec_q), 'n_should_refuse': len(no_q), 'alpha': round(alpha([v for labs in grades.values() for v in labs.values()]), 3),
               'control_mean': round(mean(control), 3), 'pool_mean': round(mean(pooled), 3), 'failures': failures, 'cost_usd_list': round(cost, 2),
               'pool_size_mean': round(mean([len(p['labs']) for p in pools.values()]), 1), 'timing': rankings['timing_s_per_query_excl_embedding'],
               'per_query': {i: {n: round(scores[n][i], 3) for n in NAMES} for i in ids}}
    (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in metrics.items() if k not in ('per_query', 'should_recommend', 'should_votes')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
