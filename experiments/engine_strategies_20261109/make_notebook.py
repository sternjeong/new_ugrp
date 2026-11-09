import json, sys
code = r'''
import json, glob, time, subprocess, sys, importlib.util
if importlib.util.find_spec('sentence_transformers') is None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'sentence-transformers'])
import numpy as np, torch
from sentence_transformers import SentenceTransformer, CrossEncoder
assert torch.cuda.is_available()
p = json.load(open(glob.glob('/kaggle/input/**/packet.json', recursive=True)[0]))
model = SentenceTransformer('BAAI/bge-m3', device='cuda'); model.half()
enc = lambda t, b=32: np.asarray(model.encode(list(t), batch_size=b, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
t0 = time.time(); V = enc(p['chunks'], 16); print('chunks', V.shape, time.time() - t0, flush=True)
D = enc(p['docs'])
# phrase x lab documents (service method)
E = enc(p['doc_phrases'])
S = E @ D.T
starts = np.array(p['starts']); topic_of = p['topic_of']
sims = np.maximum.reduceat(S, starts, axis=1)
ends = list(p['starts'][1:]) + [S.shape[1]]
best = np.full(sims.shape, -1, dtype=int)
for li, (a, b) in enumerate(zip(p['starts'], ends)):
    cols = [k for k in range(a, b) if topic_of[k] >= 0]
    if cols:
        arg = S[:, cols].argmax(axis=1)
        best[:, li] = [topic_of[cols[j]] for j in arg]
json.dump({'lab_ids': p['lab_ids'], 'sims': {x: [round(float(v), 5) for v in sims[i]] for i, x in enumerate(p['doc_phrases'])},
           'best': {x: [int(v) for v in best[i]] for i, x in enumerate(p['doc_phrases'])}}, open('doc_sims.json', 'w'), ensure_ascii=False)
# phrase x lab chunks, aggregated per professor as in curri/rag/retrieve.py (weights 1, 0.3, 0.15)
lab_kinds = {'profile', 'intro', 'paper'}
owners = sorted({o for o, k in zip(p['owners'], p['kinds']) if k in lab_kinds})
idx = {o: [i for i, (x, k) in enumerate(zip(p['owners'], p['kinds'])) if x == o and k in lab_kinds] for o in owners}
W = np.array([1.0, 0.3, 0.15])
def agg(q):
    s = V @ q
    out = {}
    for o, ids in idx.items():
        top = np.sort(s[ids])[::-1][:3]
        out[o] = float((W[:len(top)] * top).sum())
    return out
Q = enc(p['chunk_phrases'])
json.dump({'owners': owners, 'sims': {x: [round(agg(Q[i])[o], 5) for o in owners] for i, x in enumerate(p['chunk_phrases'])}}, open('chunk_sims.json', 'w'), ensure_ascii=False)
print('chunk agg done', time.time() - t0, flush=True)
# reranker over every lab: query vs the lab's three closest chunks
ce = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512, device='cuda')
ce.model.half()
R = enc(p['rerank_queries'])
out = {}
for qi, text in enumerate(p['rerank_queries']):
    s = V @ R[qi]
    pairs = []
    for o in owners:
        top = np.array(idx[o])[np.argsort(s[idx[o]])[::-1][:3]]
        pairs.append((text, '\n'.join(p['chunks'][int(k)] for k in top)[:1600]))
    scores = ce.predict(pairs, batch_size=48, show_progress_bar=False)
    out[text] = [round(float(x), 4) for x in scores]
json.dump({'owners': owners, 'scores': out}, open('rerank.json', 'w'), ensure_ascii=False)
print('done', time.time() - t0)
'''
nb = {'cells': [{'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': code.strip().splitlines(True)}],
      'metadata': {'accelerator': 'GPU', 'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'},
                   'gpuhub': {'inputs': ['packet.json']}}, 'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open(sys.argv[1], 'w'))
