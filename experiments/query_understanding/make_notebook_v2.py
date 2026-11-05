import json
cells = []
def md(s): cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': s.strip('\n').splitlines(True)})
def code(s): cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': s.strip('\n').splitlines(True)})
md("# 질의 해석 파이프라인 대조 실험 v2: 구절 × 연구실 유사도 계산\n\n로컬에서 L0~L2를 계산해 만든 `phrases_v2.json`(구절 목록)을 bge-m3로 임베딩하고, 연구실 문서(0: 프로필, 1: +대표 논문)와의 최대 코사인 유사도 행렬을 저장한다. 해석·라우팅·평가는 로컬에서 한다.")
code("""
import torch
print('GPU 사용 가능:', torch.cuda.is_available())
""")
code("!pip install -q sentence-transformers")
code("""
import os, glob, shutil
need = ['lab_profiles.jsonl', 'papers_app.jsonl', 'phrases_v2.json']
if os.path.exists('/kaggle/input'):
    for f in need:
        hits = glob.glob(f'/kaggle/input/**/{f}', recursive=True)
        if not os.path.exists(f) and hits:
            shutil.copy(hits[0], f)
assert all(os.path.exists(f) for f in need), need
""")
code("""
import json, time
import numpy as np
from collections import defaultdict
from sentence_transformers import SentenceTransformer
load = lambda p: [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]
labs = [p for p in load('lab_profiles.jsonl') if p.get('status') != 'insufficient']
lab_ids = [p['lab_id'] for p in labs]
papers = defaultdict(list)
for r in load('papers_app.jsonl'):
    papers[r['lab_id']].append(r)
phrases = json.load(open('phrases_v2.json', encoding='utf-8'))
def prof_docs(p):
    d = [p['summary_ko']] if p.get('summary_ko') else []
    return d + [f"{t['label_ko']}: {t['quote'][:400]}" for t in p['topics']]
DOCS = {'0': {l: prof_docs(p) for l, p in zip(lab_ids, labs)}}
DOCS['1'] = {l: DOCS['0'][l] + [f"{r['title']}. {r['abstract'][:500]}".strip() for r in papers.get(l, [])] for l in lab_ids}
device = 'cuda' if torch.cuda.is_available() else 'cpu'
emb = SentenceTransformer('BAAI/bge-m3', device=device)
if device == 'cuda':
    emb.half()
enc = lambda t: np.asarray(emb.encode(t, batch_size=32, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
E = enc(phrases)
out = {}
for v, per in DOCS.items():
    texts, starts = [], []
    for l in lab_ids:
        starts.append(len(texts)); texts.extend(per[l])
    S = np.maximum.reduceat(E @ enc(texts).T, np.array(starts), axis=1)
    out[v] = {p: [round(float(x), 5) for x in row] for p, row in zip(phrases, S)}
json.dump({'lab_ids': lab_ids, 'sims': out}, open('sims_v2.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('저장', len(phrases), '구절 ×', len(lab_ids), '연구실')
""")
nb = {'cells': cells, 'metadata': {'accelerator': 'GPU', 'kernelspec': {'display_name': 'Python 3', 'name': 'python3'}, 'language_info': {'name': 'python'},
      'gpuhub': {'inputs': ['data/lab_profiles.jsonl', 'experiments/query_understanding/papers_app.jsonl', 'experiments/query_understanding/phrases_v2.json']}}, 'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open('query_understanding_v2.ipynb', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
