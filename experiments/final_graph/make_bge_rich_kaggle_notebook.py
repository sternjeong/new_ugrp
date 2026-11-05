"""Create the Kaggle GPU notebook for the frozen rich BGE top-one comparison."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "bge_rich_kaggle.ipynb"

CODE = r'''
import hashlib, json, platform
from pathlib import Path
import numpy as np
import torch
import sentence_transformers, transformers
from sentence_transformers import SentenceTransformer

assert torch.cuda.is_available(), "This experiment requires a Kaggle GPU"
matches = list(Path('/kaggle/input').rglob('final_courses.jsonl'))
assert len(matches) == 1, matches
INPUT = matches[0].parent
OUTPUT = Path('/kaggle/working')
def read_jsonl(name):
    return [json.loads(line) for line in (INPUT / name).read_text(encoding='utf-8').splitlines()]
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

packet = json.loads((INPUT / 'packet.json').read_text(encoding='utf-8'))
eligibility = json.loads((INPUT / 'complete_subset_v1.json').read_text(encoding='utf-8'))
for name, expected in eligibility['source_hashes'].items():
    assert sha(INPUT / name) == expected, name
selected_labs = set(packet['labs'])
eligible_rows = set(eligibility['eligible_course_source_rows'])
courses = [('course:' + row['course_code'].strip().upper(), row)
           for no, row in enumerate(read_jsonl('final_courses.jsonl'), 1) if no in eligible_rows]
labs = [('lab:' + row['advisor_id'], row) for row in read_jsonl('final_labs.jsonl')
        if 'lab:' + row['advisor_id'] in selected_labs]
assert len(courses) == 941 and len(labs) == 136

course_chunks, course_owners = [], []
for course_id, row in courses:
    title = row['course_title']
    for value in ((row.get('description') or '')[:1000],
                  (row.get('Lecture progress plan') or '')[:1000]):
        if value.strip():
            course_chunks.append(f'{title} | {value}')
            course_owners.append(course_id)
lab_chunks, lab_owners = [], []
for lab_id, row in labs:
    intro = (row.get('research_intro') or '')[:1200]
    if intro.strip():
        lab_chunks.append(intro)
        lab_owners.append(lab_id)
    for paper in (row.get('representative_papers') or [])[:5]:
        title = paper.get('title') or ''
        abstract = (paper.get('abstract') or '')[:400]
        if title.strip() and abstract.strip():
            lab_chunks.append(f'{title} | {abstract}')
            lab_owners.append(lab_id)

revision = '5617a9f61b028005a4858fdac845db406aefb181'
model = SentenceTransformer('BAAI/bge-m3', revision=revision, device='cuda')
model.max_seq_length = 256
assert model.tokenizer.truncation_side == 'right'
cvec = model.encode(course_chunks, batch_size=16, normalize_embeddings=True,
                    show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
lvec = model.encode(lab_chunks, batch_size=16, normalize_embeddings=True,
                    show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
similarity = lvec @ cvec.T
cindex = {cid: [i for i, owner in enumerate(course_owners) if owner == cid] for cid, _ in courses}
lindex = {lid: [i for i, owner in enumerate(lab_owners) if owner == lid] for lid, _ in labs}
rule_rows = {row['lab_id']: row for row in json.loads((INPUT / 'rankings.json').read_text(encoding='utf-8'))}
assert set(rule_rows) >= selected_labs
output = []
for lab_id, _ in labs:
    rule_scores = {item['course_id']: item['score'] for item in rule_rows[lab_id]['b1']}
    items = []
    for course_id, _ in courses:
        dense = float(similarity[np.ix_(lindex[lab_id], cindex[course_id])].max())
        boost = 0.08 if course_id in rule_scores else 0.0
        items.append({'course_id': course_id, 'dense_score': round(dense, 6),
                      'rule_boost': boost, 'hybrid_score': round(dense + boost, 6)})
    dense_rank = sorted(items, key=lambda x: (-x['dense_score'], x['course_id']))[:30]
    hybrid_rank = sorted(items, key=lambda x: (-x['hybrid_score'], x['course_id']))[:30]
    output.append({'lab_id': lab_id, 'dense': dense_rank,
                   'dense_plus_frozen_rule': hybrid_rank})
rank_path = OUTPUT / 'bge_rich_rankings.json'
rank_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
manifest = {
    'status': 'unjudged_exploratory_ranking', 'model': 'BAAI/bge-m3',
    'model_revision': revision, 'device': str(next(model.parameters()).device),
    'model_max_seq_length': 256, 'course_chunks': len(course_chunks),
    'lab_chunks': len(lab_chunks), 'courses': len(courses), 'labs': len(labs),
    'source_hashes': eligibility['source_hashes'],
    'packet_sha256': sha(INPUT / 'packet.json'),
    'rule_rankings_sha256': sha(INPUT / 'rankings.json'),
    'ranking_sha256': sha(rank_path),
    'torch': torch.__version__, 'sentence_transformers': sentence_transformers.__version__,
    'transformers': transformers.__version__, 'numpy': np.__version__,
    'python': platform.python_version(), 'cuda_name': torch.cuda.get_device_name(0),
    'scope': 'bounded-window adaptation; not old notebook topic-profile chunks',
}
(OUTPUT / 'bge_rich_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False, indent=2))
'''


def main() -> None:
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": [
                "# Final rich subset BGE-M3 GPU rankings\n",
                "Frozen bounded-window top-one comparison. Rankings require two Luna relevance labels.\n",
            ]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["%pip -q install sentence-transformers==6.1.0\n"]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": [line + "\n" for line in CODE.strip().splitlines()]},
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"},
                     "gpuhub": {"inputs": [
                         "final_courses.jsonl", "final_labs.jsonl",
                         "experiments/final_graph/results/complete_subset_v1.json",
                         "experiments/final_graph/results/holdout_relevance_v1/packet.json",
                         "experiments/final_graph/results/holdout_relations_v15/rankings.json",
                     ]}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    compile(CODE, str(OUT), "exec")
    OUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
