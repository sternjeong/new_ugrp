"""Compare the frozen retrieval policies using GPU-produced BGE-M3 scores."""
import json
import random
import sys
from pathlib import Path

import numpy as np
from curri.curated_catalog import COURSE_CUE, CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
data = json.loads((OUT / 'queries.json').read_text())
z = np.load(sys.argv[1])
ids = z['lab_ids'].tolist()
assert z['scores'].shape == (len(data['phrases']), len(ids))
scores = {p: dict(zip(ids, map(float, values))) for p, values in zip(data['phrases'], z['scores'])}
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
assert set(ids) == set(catalog.profiles)
class Broker:
    def request(self, phrases, timeout):
        return {p: {'sims': scores[p], 'best': {}} for p in phrases}
engine = CuratedQueryEngine(catalog, Broker())
titles = sorted(catalog.courses, key=lambda c: (-len(c['title']), c['code']))
rows = []
for case in data['rows']:
    parsed = case['parsed']
    actual = engine.search(case['query'])
    plan = {'likes': parsed['likes'], 'dislikes': parsed['dislikes'], 'norm': parsed['norm']}
    base_ids = [c['id'] for c in actual['labs']]
    match = next((c for c in titles if c['title'].casefold() in case['query'].casefold()), None)
    if match and parsed['intent'] == 'search':
        cue = bool(COURSE_CUE.search(parsed['norm']))
        existing = catalog.courses_named(parsed['likes'], cue)
        named = [(match, True)] + [(c, exact) for c, exact in existing if c['code'] != match['code']]
        linked = {lid: link for lid, link in catalog.course_labs(named).items()
                  if not engine.conflicts_with_dislikes(lid, parsed['dislikes'])}
        dictionary = [c['id'] for c in engine.dictionary_cards(plan, case['query'])]
        phrases = list(dict.fromkeys(parsed['likes'] + parsed['dislikes'] + [parsed['norm']]))
        ranking, _, _ = engine.embedding_ranking(plan, Broker().request(phrases, 6))
        proposed = engine.fuse(linked, True, dictionary, ranking)[:10]
        proposed = [lid for lid in proposed if not engine.conflicts_with_dislikes(lid, parsed['dislikes'])]
    else:
        proposed = base_ids
    target = set(case['teachers'])
    rows.append({'code': case['code'], 'style': case['style'], 'query': case['query'],
                 'base_course_identified': case['code'] in {c['code'] for c in actual.get('courses', [])},
                 'new_course_identified': bool(match and match['code'] == case['code']),
                 'base_hit1': bool(target.intersection(base_ids[:1])),
                 'base_hit5': bool(target.intersection(base_ids[:5])),
                 'new_hit1': bool(target.intersection(proposed[:1])),
                 'new_hit5': bool(target.intersection(proposed[:5])),
                 'base_top5': base_ids[:5], 'new_top5': proposed[:5]})

def summary(rs):
    keys = ['base_course_identified','new_course_identified','base_hit1','new_hit1','base_hit5','new_hit5']
    return {'n':len(rs), **{k:sum(r[k] for r in rs) / len(rs) for k in keys}}
groups = {style: summary([r for r in rows if r['style'] == style]) for style in ('class', 'application')}
groups['overall'] = summary(rows)
rng = random.Random(20261105)
by_course = {}
for r in rows: by_course.setdefault(r['code'], []).append(r)
courses = list(by_course.values())
intervals = {}
for metric in ('hit1', 'hit5'):
    diffs = []
    for _ in range(2000):
        sample = [r for _ in courses for r in rng.choice(courses)]
        diffs.append(sum(int(r['new_'+metric])-int(r['base_'+metric]) for r in sample)/len(sample))
    intervals[metric] = [float(v) for v in np.percentile(diffs, [2.5,97.5])]
result = {'groups':groups, 'paired_course_bootstrap_95pct':intervals, 'rows':rows}
(OUT / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({'groups':groups,'paired_course_bootstrap_95pct':intervals}, ensure_ascii=False, indent=2))
