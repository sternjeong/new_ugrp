"""Exploratory negative-control template: topic intent without a class cue."""
import json
from collections import Counter
from pathlib import Path

from curri.curated_catalog import COURSE_CUE, CuratedCatalog
from curri.curated_query_engine import classify_curated_query

root = Path(__file__).resolve().parents[2]
data = json.loads((Path(__file__).parent / 'queries.json').read_text())
catalog = CuratedCatalog(root / 'data/sunwoo')
titles = sorted(catalog.courses, key=lambda c: (-len(c['title']), c['code']))
count, examples = Counter(), []
for row in data['rows'][::2]:
    query = row['title'] + ' 연구에 관심이 있어요'
    plan = classify_curated_query(query)
    count['total'] += 1
    if plan['intent'] != 'search':
        count['gated'] += 1
        continue
    match = next((c for c in titles if c['title'].casefold() in query.casefold()), None)
    cue = bool(COURSE_CUE.search(plan['norm']))
    named = catalog.courses_named(plan['likes'], cue)
    linked = catalog.course_labs(named)
    led = bool(linked) and (cue or all(catalog.courses_named([p], cue) for p in plan['likes']))
    proposed_linked = bool(match and catalog.course_labs([(match, True)]))
    count['search'] += 1
    count['baseline_course_led'] += bool(led)
    count['proposed_course_led'] += proposed_linked
    if proposed_linked and not led:
        count['new_course_led'] += 1
        if len(examples) < 5:
            examples.append(query)
print(json.dumps({'counts': dict(count), 'examples': examples}, ensure_ascii=False, indent=2))
