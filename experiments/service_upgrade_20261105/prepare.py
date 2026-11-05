"""Freeze synthetic course queries and a Kaggle GPU notebook; no app data is changed."""
import hashlib
import json
import random
from pathlib import Path

from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import classify_curated_query

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
counts = {}
for c in catalog.courses:
    counts[c['title']] = counts.get(c['title'], 0) + 1
eligible = []
for c in catalog.courses:
    teachers = sorted({p['lab_id'] for p in c.get('professors', [])
                       if p.get('lab_id') in catalog.profiles and p.get('basis') != 'not_in_lab_data'})
    title = c['title'].strip()
    if teachers and counts[title] == 1 and 3 <= len(title) <= 35:
        eligible.append((c, teachers))
rng = random.Random(20261105)
chosen = rng.sample(sorted(eligible, key=lambda v: v[0]['code']), min(200, len(eligible)))
rows = []
for c, teachers in chosen:
    for style, query in [('class', f"{c['title']} 수업이 재밌었어요"),
                         ('application', f"{c['title']}에서 배운 내용을 연구에 활용하고 싶어요")]:
        parsed = classify_curated_query(query)
        rows.append({'code': c['code'], 'title': c['title'], 'department': c['department']['name'],
                     'teachers': teachers, 'style': style, 'query': query, 'parsed': parsed})
phrases = sorted({p for row in rows for p in row['parsed']['likes'] + row['parsed']['dislikes'] + [row['parsed']['norm']]})
(OUT / 'queries.json').write_text(json.dumps({'seed': 20261105, 'eligible': len(eligible), 'rows': rows, 'phrases': phrases}, ensure_ascii=False, indent=2))
source = '''import glob, json, time, platform, subprocess, sys, importlib.util
if importlib.util.find_spec('sentence_transformers') is None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'sentence-transformers'])
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
assert torch.cuda.is_available(), 'Kaggle GPU is required'
f = lambda name: glob.glob('/kaggle/input/**/' + name, recursive=True)[0]
data = json.load(open(f('queries.json')))
z = np.load(f('curated_doc_embeddings.npz'))
D = z['D'].astype(np.float32)
starts = z['lab_starts'].astype(int)
lab_ids = z['lab_ids'].tolist()
t0 = time.time()
model = SentenceTransformer('BAAI/bge-m3', device='cuda').half()
load_s = time.time() - t0
t0 = time.time()
E = model.encode(data['phrases'], batch_size=32, normalize_embeddings=True, show_progress_bar=False)
encode_s = time.time() - t0
scores = np.maximum.reduceat(np.asarray(E, dtype=np.float32) @ D.T, starts, axis=1)
np.savez_compressed('/kaggle/working/query_scores.npz', scores=scores, lab_ids=np.asarray(lab_ids))
json.dump({'gpu':torch.cuda.get_device_name(0), 'torch':torch.__version__, 'model':'BAAI/bge-m3', 'model_load_s':load_s, 'encode_s':encode_s, 'phrases':len(data['phrases']), 'documents':len(D), 'labs':len(lab_ids)}, open('/kaggle/working/run_metadata.json','w'), indent=2)
print('GPU', torch.cuda.get_device_name(0), 'phrases',len(data['phrases']), 'encode_s',encode_s)
'''
nb = {'cells': [{'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': source.splitlines(True)}],
      'metadata': {'accelerator':'GPU','kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
                   'language_info':{'name':'python'}, 'gpuhub':{'inputs':['experiments/service_upgrade_20261105/queries.json','.local/curated_doc_embeddings.npz']}},
      'nbformat':4,'nbformat_minor':5}
(OUT / 'gpu.ipynb').write_text(json.dumps(nb, ensure_ascii=False, indent=2))
for file in [OUT / 'queries.json', ROOT / '.local/curated_doc_embeddings.npz', ROOT / 'data/sunwoo/app_profiles.jsonl', ROOT / 'data/sunwoo/courses.jsonl']:
    print(file.name, hashlib.sha256(file.read_bytes()).hexdigest())
print('eligible',len(eligible),'selected courses',len(chosen),'queries',len(rows),'phrases',len(phrases))
