"""Compute the top-10 labs (or a refusal) of each strategy for every query. Writes rankings.json.

Reuses the service engine's own pieces (dictionary search, phrase ranking, RRF fusion, course links, dislike conflicts).
Run from the repo root: PYTHONPATH=.:experiments/engine_strategies_20261109 python3 experiments/engine_strategies_20261109/strategies.py <kaggle_output_dir>
"""
import json
import sys
import time
from pathlib import Path

from common import OUT, rule_parse
from curri.curated_catalog import COURSE_CUE, CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine
from curri.query_engine import LAMBDA, rrf, zscores

ROOT = OUT.parents[1]
kaggle = Path(sys.argv[1])
queries = json.loads((OUT / 'queries.json').read_text())
llm = json.loads((OUT / 'llm_parse.json').read_text())
doc = json.loads((kaggle / 'doc_sims.json').read_text())
chunk = json.loads((kaggle / 'chunk_sims.json').read_text())
rer = json.loads((kaggle / 'rerank.json').read_text())
doc_table = {p: {'sims': dict(zip(doc['lab_ids'], doc['sims'][p])), 'best': dict(zip(doc['lab_ids'], doc['best'][p]))} for p in doc['sims']}
owners = chunk['owners']
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
owners = [o for o in owners if o in catalog.profiles]
groups = {}
for row in map(json.loads, filter(str.strip, (ROOT / 'data/sunwoo/labs.jsonl').read_text(encoding='utf-8').splitlines())):
    if row.get('recommendable'):
        info = row.get('lab') or {}
        groups[row['id']] = info.get('group') or info.get('url') or row['id']   # curri/rag/corpus.py group_key


class Replay:
    def request(self, phrases, timeout, remote=True):
        return {p: doc_table[p] for p in phrases} if all(p in doc_table for p in phrases) else None


engine = CuratedQueryEngine(catalog, Replay())
chunk_all = chunk['owners']


def chunk_scores(text):
    return dict(zip(chunk_all, chunk['sims'][text]))


def chunk_ranking(positive, dislikes):
    """Labs by aggregated chunk similarity with the same z-score dislike penalty as the service engine."""
    pos = chunk_scores(positive)
    labs = [l for l in pos if l in catalog.profiles]
    score = dict(zip(labs, zscores([pos[l] for l in labs])))
    for d in dislikes:
        z = dict(zip(labs, zscores([chunk_scores(d)[l] for l in labs])))
        score = {l: s - LAMBDA * max(0.0, z[l]) for l, s in score.items()}
    return sorted(labs, key=lambda l: -score[l])


def rerank(ids, text, top=30):
    scores = dict(zip(rer['owners'], rer['scores'][text]))
    head = sorted(ids[:top], key=lambda l: -scores.get(l, -99))
    return head + ids[top:]


def build(q, parse, clean, signals, reranker):
    """parse: 'rule' | 'llm'; signals: subset of {'doc', 'rawdoc', 'chunk'}."""
    if parse == 'rule':
        p = rule_parse(q['text'], clean)
        if p['intent'] != 'search':
            return None
        likes, dislikes, norm, search = p['likes'], p['dislikes'], p['norm'], None
        cue = bool(COURSE_CUE.search(norm))
    else:
        L = llm[q['id']]
        if L['intent'] != 'search':
            return None
        likes, dislikes, norm, search = L['likes'] or [L['search_text']], L['dislikes'], q['text'], L['search_text']
        cue = bool(COURSE_CUE.search(q['text']))
    plan = {'likes': likes, 'dislikes': dislikes, 'norm': norm}
    cards = engine.catalog.search(search or ' '.join(likes) or q['text'])
    cards = [c for c in cards if not engine.conflicts_with_dislikes(c['id'], dislikes)]
    courses = catalog.courses_named(likes, cue)
    linked = {l: v for l, v in catalog.course_labs(courses).items() if not engine.conflicts_with_dislikes(l, dislikes)}
    led = bool(linked) and (cue or all(catalog.courses_named([x], cue) for x in likes))
    lists = [[c['id'] for c in cards]] if cards else []
    if 'doc' in signals:
        sims = {x: doc_table[x] for x in dict.fromkeys(likes + dislikes + [norm])}
        lists.append(engine.embedding_ranking(plan, sims)[0])
    if 'rawdoc' in signals:
        lists.append(sorted((l for l in doc_table[norm]['sims'] if l in catalog.profiles), key=lambda l: -doc_table[norm]['sims'][l]))
    if 'chunk' in signals:
        positive = search if parse == 'llm' else (' '.join(likes) if dislikes else q['text'])
        lists.append(chunk_ranking(positive, dislikes))
    fused = CuratedQueryEngine.fuse(linked, led, *lists)
    fused = [l for l in fused if not engine.conflicts_with_dislikes(l, dislikes)]
    if reranker:
        fused = rerank(fused, search if parse == 'llm' else q['text'])
    return fused[:10]


def vector_only(q):
    """Teammate's retrieval: raw text, fold co-led labs, relative floor."""
    s = chunk_scores(q['text'])
    order = sorted((l for l in s if l in catalog.profiles), key=lambda l: -s[l])
    out, seen = [], set()
    best = s[order[0]]
    for l in order:
        g = groups.get(l, l)
        if g in seen:
            continue
        seen.add(g)
        if len(out) >= 5 and s[l] < best * 0.8:
            break
        out.append(l)
    return out[:10]


def current(q):
    found = engine.search(q['text'])
    return [c['id'] for c in found['labs']][:10] if found['intent'] == 'search' else None


STRATEGIES = {'A0': current,
              'A1': lambda q: build(q, 'rule', True, {'doc'}, False),
              'A2': lambda q: build(q, 'rule', True, {'doc', 'rawdoc'}, False),
              'V': vector_only,
              'A3': lambda q: build(q, 'rule', True, {'chunk'}, False),
              'A4': lambda q: build(q, 'rule', True, {'doc', 'chunk'}, False),
              'A5': lambda q: build(q, 'llm', False, {'chunk'}, False),
              'A6': lambda q: build(q, 'rule', True, {'doc', 'chunk'}, True),
              'A7': lambda q: build(q, 'llm', False, {'chunk'}, True)}
result, timing = {}, {}
for name, fn in STRATEGIES.items():
    t0 = time.perf_counter()
    result[name] = {q['id']: fn(q) for q in queries}
    timing[name] = round((time.perf_counter() - t0) / len(queries), 4)
(OUT / 'rankings.json').write_text(json.dumps({'rankings': result, 'timing_s_per_query_excl_embedding': timing}, ensure_ascii=False, indent=1))
print(timing)
for name in result:
    declined = [k for k, v in result[name].items() if not v]
    print(name, 'declined', len(declined), declined[:16])
