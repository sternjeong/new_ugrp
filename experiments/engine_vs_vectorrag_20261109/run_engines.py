"""Run both engines on every query with the Kaggle vectors and write top-10 lab lists (rankings.json).

H is the service's CuratedQueryEngine with a broker replaying the computed phrase similarities. V is the teammate's
own curri/rag code (FileIndex + retrieve.search) from the extracted branch, with his relative floor.

Run from the repo root: PYTHONPATH=. python3 experiments/engine_vs_vectorrag_20261109/run_engines.py <proto_dir> <kaggle_output_dir>
"""
import json
import resource
import shutil
import sys
import time
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
proto, kaggle = Path(sys.argv[1]), Path(sys.argv[2])
queries = json.loads((OUT / 'queries.json').read_text())

# ---- H: the service engine ----
data = json.loads((kaggle / 'phrase_sims.json').read_text())
lab_ids = data['lab_ids']
table = {p: {'sims': dict(zip(lab_ids, data['sims'][p])), 'best': dict(zip(lab_ids, data['best'][p]))} for p in data['sims']}


class Replay:
    def request(self, phrases, timeout, remote=True):
        return {p: table[p] for p in phrases} if all(p in table for p in phrases) else None


catalog = CuratedCatalog(ROOT / 'data/sunwoo')
engine = CuratedQueryEngine(catalog, Replay())
h_rows, h_time = {}, []
for q in queries:
    t0 = time.perf_counter()
    found = engine.search(q['text'])
    h_time.append(time.perf_counter() - t0)
    h_rows[q['id']] = {'mode': found['mode'], 'labs': [c['id'] for c in found['labs']][:10], 'likes': found['interpretation']['likes'],
                       'dislikes': found['interpretation']['dislikes']}

# ---- V: the teammate's code, loaded from his branch under its own package name ----
index_dir = proto / 'data/rag/pack300-whole'
if not (index_dir / 'vectors.f32').exists():
    shutil.copy(kaggle / 'vectors.f32', index_dir / 'vectors.f32')
sys.path.insert(0, str(proto / 'curri'))
from rag import index, retrieve  # noqa: E402  (the teammate's package, imported as `rag`)
t0 = time.perf_counter()
idx = index.FileIndex.load(index_dir)
v_load = time.perf_counter() - t0
vectors = json.loads((kaggle / 'query_vectors.json').read_text())


class Stored:
    def embed(self, texts):
        return [vectors[t] for t in texts]


MIN_CARDS, MAX_CARDS, RELATIVE_FLOOR = 5, 20, 0.8  # curri/rag/engine.py
v_rows, v_time, v_gold = {}, [], {}
for q in queries:
    t0 = time.perf_counter()
    cards = retrieve.search(idx, Stored(), q['text'])
    v_time.append(time.perf_counter() - t0)
    best, labs = cards[0]['score'], []
    for n, rank in enumerate(cards[:MAX_CARDS]):
        if n >= MIN_CARDS and rank['score'] < best * RELATIVE_FLOOR:
            break
        labs.append(rank['members'][0]['lab_id'])
    v_rows[q['id']] = {'mode': 'vector', 'labs': labs[:10]}
    v_gold[q['id']] = [r[1] for r in retrieve.rank_professors(idx, vectors[q['text']])[:20]]

mean = lambda xs: round(sum(xs) / len(xs), 4)
result = {'H': h_rows, 'V': v_rows, 'V_professor_rank': v_gold,
          'timing': {'H_search_s_mean': mean(h_time), 'V_search_s_mean': mean(v_time), 'V_index_load_s': round(v_load, 2),
                     'peak_rss_mb_both': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024}}
(OUT / 'rankings.json').write_text(json.dumps(result, ensure_ascii=False, indent=1))
print(result['timing'])
overlap = [len(set(h_rows[q['id']]['labs']) & set(v_rows[q['id']]['labs'])) for q in queries]
print('mean overlap of top 10:', mean(overlap), '| H modes:', {m: sum(r['mode'] == m for r in h_rows.values()) for m in {r['mode'] for r in h_rows.values()}},
      '| H empty:', [k for k, r in h_rows.items() if not r['labs']])
