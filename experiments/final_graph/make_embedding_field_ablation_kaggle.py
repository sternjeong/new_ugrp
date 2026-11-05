"""Generate a CUDA-only Kaggle notebook for the frozen field ablation profiles."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "embedding_field_ablation_kaggle.ipynb"

CODE = r'''
import hashlib, json, platform, statistics
from pathlib import Path
import numpy as np
import torch
import sentence_transformers, transformers
from sentence_transformers import SentenceTransformer

assert torch.cuda.is_available(), 'Kaggle GPU required; CPU embedding inference forbidden'
paths = list(Path('/kaggle/input').rglob('profiles.json'))
assert len(paths) == 1, paths
INPUT = paths[0].parent
OUTPUT = Path('/kaggle/working')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
profiles_path = INPUT / 'profiles.json'
source_manifest_path = INPUT / 'profiles_manifest.json'
frame_path = INPUT / 'frame.json'
source_manifest = json.loads(source_manifest_path.read_text(encoding='utf-8'))
assert sha(profiles_path) == source_manifest['profiles_sha256']
profiles = json.loads(profiles_path.read_text(encoding='utf-8'))
frame = json.loads(frame_path.read_text(encoding='utf-8'))
labs, courses = profiles['labs'], profiles['courses']
assert len(labs) == 180 and len(courses) == 941
assert {x['id'] for x in labs} == {lid for items in frame['buckets'].values() for item in items for lid in item['lab_ids']}

revision = '5617a9f61b028005a4858fdac845db406aefb181'
model = SentenceTransformer('BAAI/bge-m3', revision=revision, device='cuda')
model.max_seq_length = 256
assert str(next(model.parameters()).device).startswith('cuda')
assert model.tokenizer.truncation_side == 'right'

lab_chunks, course_chunks = [], []
lab_ix, course_ix = {}, {}
for group, chunks, index in ((labs, lab_chunks, lab_ix), (courses, course_chunks, course_ix)):
    for entity in group:
        index[entity['id']] = {}
        for field in (('core','admin') if group is labs else ('core','admin','learning_context')):
            start = len(chunks)
            chunks.extend(entity[field])
            index[entity['id']][field] = list(range(start,len(chunks)))

def lengths(chunks):
    tokens = [len(model.tokenizer(x, truncation=False)['input_ids']) for x in chunks]
    chars = [len(x) for x in chunks]
    return {'chunks':len(chunks), 'char_median':statistics.median(chars),
            'char_p95':sorted(chars)[int(.95*(len(chars)-1))],
            'token_median':statistics.median(tokens),
            'token_p95':sorted(tokens)[int(.95*(len(tokens)-1))],
            'token_truncated_256':sum(x>256 for x in tokens)}
distribution = {}
for kind, group in (('lab',labs),('course',courses)):
    for field in (('core','admin') if kind=='lab' else ('core','admin','learning_context')):
        arr = [chunk for entity in group for chunk in entity[field]]
        distribution[kind+'_'+field] = lengths(arr)

lvec = model.encode(lab_chunks, batch_size=16, normalize_embeddings=True,
                    show_progress_bar=True, convert_to_tensor=True)
cvec = model.encode(course_chunks, batch_size=16, normalize_embeddings=True,
                    show_progress_bar=True, convert_to_tensor=True)
assert lvec.is_cuda and cvec.is_cuda
sim = (lvec.float() @ cvec.float().T).cpu().numpy()

variants = {
    'core':(('core',),('core',)),
    'lab_admin':(('core','admin'),('core',)),
    'course_admin':(('core',),('core','admin')),
    'both_admin':(('core','admin'),('core','admin')),
    'learning_context':(('core',),('core','learning_context')),
}
course_ids = [x['id'] for x in courses]
def indices(index, entity_id, names):
    return [i for name in names for i in index[entity_id][name]]
rankings = []
for lab in labs:
    lab_id = lab['id']
    ranked = {'lab_id':lab_id}
    for variant, (lab_fields,course_fields) in variants.items():
        li = indices(lab_ix,lab_id,lab_fields)
        assert li
        best = sim[li].max(axis=0)
        scores = []
        for course_id in course_ids:
            ci = indices(course_ix,course_id,course_fields)
            assert ci
            scores.append((float(best[ci].max()),course_id))
        scores.sort(key=lambda x:(-x[0],x[1]))
        ranked[variant] = [{'course_id':cid,'score':round(score,6)} for score,cid in scores[:30]]
    rankings.append(ranked)
rank_path = OUTPUT / 'embedding_field_rankings.json'
rank_path.write_text(json.dumps(rankings,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
manifest = {
    'status':'unjudged_field_ablation_rankings',
    'model':'BAAI/bge-m3','model_revision':revision,
    'encoder_api':'SentenceTransformer.encode(normalize_embeddings=True,convert_to_tensor=True)',
    'pooling':'model default dense sentence embedding',
    'aggregation':'max cosine over lab and course chunks',
    'device':str(next(model.parameters()).device),
    'cuda_name':torch.cuda.get_device_name(0),
    'max_seq_length':model.max_seq_length,'batch_size':16,
    'profiles_sha256':sha(profiles_path),'profiles_manifest_sha256':sha(source_manifest_path),
    'frame_sha256':sha(frame_path),
    'rankings_sha256':sha(rank_path),'distribution':distribution,
    'lab_chunks':len(lab_chunks),'course_chunks':len(course_chunks),
    'labs':len(labs),'courses':len(courses),
    'torch':torch.__version__,'transformers':transformers.__version__,
    'sentence_transformers':sentence_transformers.__version__,
    'numpy':np.__version__,'python':platform.python_version(),
}
(OUTPUT/'embedding_field_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:manifest[k] for k in ('device','cuda_name','profiles_sha256','rankings_sha256','labs','courses','lab_chunks','course_chunks')},ensure_ascii=False))
'''


def main():
    nb = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": [
                "# Field controlled lab-course embedding ablation\n",
                "Frozen profiles; CUDA required. No labels or method keys are loaded.\n"]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["%pip -q install sentence-transformers==6.1.0\n"]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": [line + "\n" for line in CODE.strip().splitlines()]},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"},
                     "gpuhub": {"inputs": [
                         "experiments/final_graph/results/embedding_field_ablation_v1/profiles.json",
                         "experiments/final_graph/results/embedding_field_ablation_v1/profiles_manifest.json",
                         "experiments/final_graph/results/embedding_field_ablation_v1/frame.json",
                     ]}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    compile(CODE, str(OUT), "exec")
    OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
