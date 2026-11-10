"""Run the service's own engine over the 100 study queries with answers recorded from the real worker code.

packet <out.json>:   the jobs the engine would send to the worker.
evaluate <answers.json>: replay them, write service_rankings.json. Run from the repo root with PYTHONPATH=.
"""
import json
import sys
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine
from curri.embed_broker import query_key

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def queries():
    return json.loads((ROOT / 'experiments/engine_strategies_20261109/queries.json').read_text()) + json.loads((HERE / 'holdout.json').read_text())


class Recorder:
    def __init__(self):
        self.jobs = {}

    def understand(self, phrases, query, timeout, remote=True):
        self.jobs[query['raw']] = {'phrases': phrases, 'query': query}


class Replay:
    def __init__(self, answers):
        self.answers = answers

    def understand(self, phrases, query, timeout, remote=True):
        a = self.answers[query['raw']]
        found = {p: {'sims': dict(zip(a['lab_ids'], a['sims'][p])), 'best': dict(zip(a['lab_ids'], a['best'][p]))} for p in phrases}
        found[query_key(query)] = a['query']
        return found


def score():
    """Fit of the service engine on the held-out set, on the panel's grades. A lab the panel never saw counts 0 and is listed."""
    import math
    from collections import defaultdict
    hold = json.loads((HERE / 'holdout.json').read_text())
    pools = json.loads((HERE / 'test_pools.json').read_text())
    saved = json.loads((HERE / 'test_rankings.json').read_text())
    service = json.loads((HERE / 'service_rankings.json').read_text())
    mean = lambda v: sum(v) / len(v) if v else 0.0
    dcg = lambda g: sum(x / math.log2(i + 2) for i, x in enumerate(g))
    grades, votes = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for path in sorted((HERE / 'test_calls').glob('*.json')) + sorted((HERE / 'service_calls').glob('*.json')):
        r = json.loads(path.read_text())
        if r.get('ok'):
            if path.parent.name == 'test_calls':
                votes[path.name.split('_j')[0]].append(r['value']['should_recommend'])
            for g in r['value']['grades']:
                grades[path.name.split('_j')[0].split('__')[-1]][r['key'][g['label']]].append(g['grade'])
    gain = {k: {l: mean(v) for l, v in x.items()} for k, x in grades.items()}
    should = {k: sum(v) > len(v) / 2 for k, v in votes.items()}

    def fit(rank):
        out = {}
        for q in hold:
            k, top = q['id'], (rank[q['id']] or [])[:5]
            if should[k]:
                ideal = dcg(sorted((v for l, v in gain[k].items() if l not in pools[k]['controls']), reverse=True)[:5]) or 1
                out[k] = dcg([gain[k].get(l, 0) for l in top]) / ideal
            else:
                out[k] = 1.0 if not top else 0.0
        return out
    runs = {**saved, 'service': {k: v['labs'] for k, v in service.items() if k in should}}
    table = {name: round(mean(list(fit(r).values())), 3) for name, r in runs.items()}
    unseen = {q['id']: [l for l in (runs['service'][q['id']] or [])[:5] if l not in gain[q['id']]] for q in hold if should[q['id']]}
    wrong = [k for k in should if should[k] and not runs['service'][k]], [k for k in should if not should[k] and runs['service'][k]]
    same = mean([len(set((runs['service'][k] or [])[:5]) & set((saved['N1'][k] or [])[:5])) / 5 for k in should if saved['N1'][k]])
    result = {'fit': table, 'unjudged_pairs': sum(map(len, unseen.values())), 'wrong_refusals': wrong[0], 'missed_refusals': wrong[1], 'top5_overlap_with_study_N1': round(same, 3)}
    (HERE / 'service_metrics.json').write_text(json.dumps({**result, 'unseen': unseen, 'per_query': fit(runs['service'])}, ensure_ascii=False, indent=1))
    print(json.dumps(result, ensure_ascii=False))


def main(command, path=None):
    if command == 'score':
        return score()
    catalog = CuratedCatalog(ROOT / 'data/sunwoo')
    if command == 'packet':
        recorder = Recorder()
        engine = CuratedQueryEngine(catalog, recorder)
        for q in queries():
            engine.search(q['text'])
        Path(path).write_text(json.dumps(list(recorder.jobs.values()), ensure_ascii=False))
        print('jobs', len(recorder.jobs))
    else:
        engine = CuratedQueryEngine(catalog, Replay(json.loads(Path(path).read_text())))
        out = {}
        for q in queries():
            found = engine.search(q['text'])
            out[q['id']] = {'intent': found['intent'], 'labs': [c['id'] for c in found['labs']]}
        (HERE / 'service_rankings.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
        print('queries', len(out), 'answered', sum(bool(v['labs']) for v in out.values()))


if __name__ == '__main__':
    main(*sys.argv[1:])
