"""Compare retrieval engines on the imported MVP gold set."""
import json, sys, statistics
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo' / 'legacy' / 'mvp-4dept'
sys.path.insert(0, str(ROOT))
from curri.catalog import Catalog
from curri.profile_catalog import ProfileCatalog

gold = [json.loads(l) for l in open(DATA / 'goldset.jsonl')]

def evaluate(cat, name):
    rows = []
    for g in gold:
        ids = [r['id'] for r in cat.search(g['interest'])]
        exp = set(g['expected_lab_ids'])
        if not exp:
            rows.append((g['id'], len(ids), None, None, 1.0 if not ids else 0.0)); continue
        top5 = set(ids[:5]) & exp
        p5 = len(top5) / min(5, len(exp))
        recall = len(set(ids) & exp) / len(exp)
        rows.append((g['id'], len(ids), p5, recall, None))
    p5s = [r[2] for r in rows if r[2] is not None]; recs = [r[3] for r in rows if r[3] is not None]
    print(f'== {name}: mean hits@5 {statistics.mean(p5s):.2f} · recall {statistics.mean(recs):.2f} · median results {statistics.median(r[1] for r in rows):.0f} · empty-control ok {[r[4] for r in rows if r[4] is not None]}')
    return {r[0]: r for r in rows}

if __name__ == '__main__':
    old = evaluate(Catalog(DATA), 'rule-based Catalog')
    new = evaluate(ProfileCatalog(DATA), 'ProfileCatalog')
    print(f"{'id':4} {'interest':44} {'old n':>5} {'old@5':>6} {'new n':>5} {'new@5':>6} {'new rec':>7}")
    for g in gold:
        o, n = old[g['id']], new[g['id']]
        f = lambda v: '-' if v is None else f'{v:.2f}'
        print(f"{g['id']:4} {g['interest'][:44]:44} {o[1]:>5} {f(o[2]):>6} {n[1]:>5} {f(n[2]):>6} {f(n[3]):>7}")
