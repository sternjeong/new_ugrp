"""질의 해석 실험 평가. 사용: python3 evaluate.py [ranks_v1.json]  (저장소 루트에서 실행)
A(현재 앱)는 ProfileCatalog.search로 직접 계산하고, 나머지 방법은 노트북이 만든 ranks를 읽는다."""
import sys, json, math, collections as C
sys.path.insert(0, '.')
from curri.profile_catalog import ProfileCatalog

Q = json.load(open('experiments/query_understanding/queries.json', encoding='utf-8'))
labs = [json.loads(l) for l in open('data/lab_profiles.jsonl', encoding='utf-8')]
labs = [p for p in labs if p['status'] != 'insufficient']
prim = {p['lab_id']: {t['concept'] for t in p['topics'] if t.get('weight', 'primary') == 'primary'} for p in labs}
K = 5

def group_hit(lid, g): return bool(prim[lid] & set(g))
def relevant(lid, q): return any(group_hit(lid, g) for g in q['pos'])
def violation(lid, q): return bool(prim[lid] & set(q['neg'])) and not relevant(lid, q)

def ndcg(top, q):
    gains = [1 if relevant(l, q) else 0 for l in top[:K]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    n_rel = sum(1 for l in prim if relevant(l, q))
    idcg = sum(1 / math.log2(i + 2) for i in range(min(K, n_rel)))
    return dcg / idcg if idcg else 0.0

def metrics(top, q):
    top = top[:K]
    m = {'p5': sum(relevant(l, q) for l in top) / K, 'ndcg5': ndcg(top, q)}
    if q['neg']:
        m['viol5'] = sum(violation(l, q) for l in top) / K
        m['viol_any'] = float(any(violation(l, q) for l in top))
    if len(q['pos']) > 1:
        m['cover'] = float(all(any(group_hit(l, g) for l in top) for g in q['pos']))
    return m

def rules_ranks():
    cat = ProfileCatalog('data')
    return {q['id']: [r['id'] for r in cat.search(q['text'])] for q in Q}

def table(ranks_by_method, methods, types):
    out = []
    for name in methods:
        row = {'method': name}
        for t in types:
            qs = [q for q in Q if t == 'all' or q['type'] == t or (t == 'negation*' and q['type'] in ('negation', 'soft_negation'))]
            ms = [metrics(ranks_by_method[name][q['id']], q) for q in qs]
            for k in ('p5', 'ndcg5', 'viol5', 'viol_any', 'cover'):
                vals = [m[k] for m in ms if k in m]
                if vals:
                    row[f'{t}:{k}'] = round(sum(vals) / len(vals), 2)
        out.append(row)
    return out

if __name__ == '__main__':
    ranks = json.load(open(sys.argv[1])) if len(sys.argv) > 1 else {}
    ranks['A'] = rules_ranks()
    types = ['simple', 'paraphrase', 'compound', 'multi', 'negation*', 'all']
    methods = ['A'] + [m for m in sorted(ranks) if m != 'A']
    rows = table(ranks, methods, types)
    cols = ['method'] + sorted({k for r in rows for k in r if k != 'method'}, key=lambda k: (types.index(k.split(':')[0]), k))
    json.dump(rows, open('experiments/query_understanding/V1/metrics_v1.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for r in rows:
        print(r['method'], {k: v for k, v in r.items() if k != 'method'})
