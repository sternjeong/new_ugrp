"""Which part of the Sonnet parse carries A5's gain? Swap intent / like-dislike split / search text one at a time.

Run from the repo root: PYTHONPATH=.:experiments/no_llm_20261109:experiments/engine_strategies_20261109 python3 experiments/no_llm_20261109/ablate.py <kaggle_dir>
"""
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import grades
from common import rule_parse
from curri.curated_catalog import COURSE_CUE, CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine
from curri.query_engine import LAMBDA, zscores

kaggle = Path(sys.argv[1])
queries, gain, should, controls = grades.load()
llm = json.loads((grades.BASE / 'llm_parse.json').read_text())
doc = json.loads((kaggle / 'doc_sims.json').read_text())
chunk = json.loads((kaggle / 'chunk_sims.json').read_text())
doc_table = {p: {'sims': dict(zip(doc['lab_ids'], doc['sims'][p])), 'best': dict(zip(doc['lab_ids'], doc['best'][p]))} for p in doc['sims']}
catalog = CuratedCatalog(grades.ROOT / 'data/sunwoo')
engine = CuratedQueryEngine(catalog, None)


def chunk_scores(text):
    return dict(zip(chunk['owners'], chunk['sims'][text]))


def chunk_ranking(positive, dislikes):
    pos = chunk_scores(positive)
    labs = [l for l in pos if l in catalog.profiles]
    score = dict(zip(labs, zscores([pos[l] for l in labs])))
    for d in dislikes:
        z = dict(zip(labs, zscores([chunk_scores(d)[l] for l in labs])))
        score = {l: s - LAMBDA * max(0.0, z[l]) for l, s in score.items()}
    return sorted(labs, key=lambda l: -score[l])


def run(q, intent, split, text, doc_signal=False, dictionary=True, course=True):
    rule, L = rule_parse(q['text'], True), llm[q['id']]
    if (L if intent == 'llm' else rule)['intent'] != 'search':
        return None
    source = L if split == 'llm' else rule
    likes, dislikes = (source['likes'] or [q['text']]), source['dislikes']
    if text == 'llm':
        positive = L['search_text'] or q['text']
    else:
        joined = ' '.join(likes)
        positive = joined if dislikes and joined in chunk['sims'] else q['text']
    cards = catalog.search(positive if text == 'llm' else ' '.join(likes)) if dictionary else []
    cards = [c for c in cards if not engine.conflicts_with_dislikes(c['id'], dislikes)]
    cue = bool(COURSE_CUE.search(q['text']))
    named = catalog.courses_named(likes, cue) if course else []
    linked = {l: v for l, v in catalog.course_labs(named).items() if not engine.conflicts_with_dislikes(l, dislikes)}
    led = bool(linked) and (cue or all(catalog.courses_named([x], cue) for x in likes))
    lists = [[c['id'] for c in cards]] if cards else []
    if doc_signal and all(p in doc_table for p in likes + dislikes + [rule['norm']]):
        lists.append(engine.embedding_ranking({'likes': likes, 'dislikes': dislikes, 'norm': rule['norm']}, {p: doc_table[p] for p in dict.fromkeys(likes + dislikes + [rule['norm']])})[0])
    lists.append(chunk_ranking(positive, [d for d in dislikes if d in chunk['sims']]))
    return [l for l in CuratedQueryEngine.fuse(linked, led, *lists) if not engine.conflicts_with_dislikes(l, dislikes)][:10]


VARIANTS = {'A4 규칙': ('rule', 'rule', 'rule', True), 'A5 전부 LLM': ('llm', 'llm', 'llm', False),
            '의도만 LLM': ('llm', 'rule', 'rule', True), '좋아함/싫어함만 LLM': ('rule', 'llm', 'rule', False), '검색문만 LLM': ('rule', 'rule', 'llm', False),
            '의도+검색문 LLM': ('llm', 'rule', 'llm', False), '의도+분리 LLM': ('llm', 'llm', 'rule', False)}
dcg = lambda g: sum(x / math.log2(i + 2) for i, x in enumerate(g))
mean = lambda v: sum(v) / len(v)
out, covered, types = {}, {}, defaultdict(list)
for q in queries:
    types[q['type']].append(q['id'])
scores = {}
for name, (i, s, t, d) in VARIANTS.items():
    per, hit, n = {}, 0, 0
    for q in queries:
        k, r = q['id'], run(q, i, s, t, d)
        top = (r or [])[:5]
        if should[k]:
            ideal = dcg(sorted((v for l, v in gain[k].items() if l not in controls[k]), reverse=True)[:5]) or 1
            per[k] = dcg([gain[k].get(l, 0) for l in top]) / ideal
            hit += sum(l in gain[k] for l in top); n += len(top)
        else:
            per[k] = 1.0 if not top else 0.0
    scores[name] = per
    rec = [q['id'] for q in queries if should[q['id']]]
    print(f"{name:18s} fit {mean(list(per.values())):.3f}  rec nDCG5 {mean([per[k] for k in rec]):.3f}  refuse-correct {sum(per[q['id']] == 1.0 for q in queries if not should[q['id']])}/{sum(not should[q['id']] for q in queries)}  judged {hit}/{n}")
print()
names = list(VARIANTS)
print('유형'.ljust(14), ' '.join(n[:7].ljust(8) for n in names))
for t, ids in types.items():
    print(t.ljust(14), ' '.join(f'{mean([scores[n][k] for k in ids]):.3f}'.ljust(8) for n in names))
(Path(__file__).parent / 'ablation.json').write_text(json.dumps(scores, ensure_ascii=False, indent=1))
