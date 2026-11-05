"""Build reusable BGE-M3 vectors for the current service catalog on Kaggle."""
import hashlib
import json
from pathlib import Path

import numpy as np

from worker import build_docs, load_jsonl


def course_documents(courses):
    ids, texts = [], []
    for row in courses:
        if not row.get('recommendable'):
            continue
        ids.append(row['code'])
        # Keep teaching content; omit enrollment rules, administration and source metadata.
        parts = [row.get('title') or '', (row.get('description') or '')[:700],
                 (row.get('lecture_plan') or '')[:700]]
        texts.append(' '.join(p.strip() for p in parts if isinstance(p, str) and p.strip()))
    return ids, texts


def main():
    from sentence_transformers import SentenceTransformer

    labs = load_jsonl('app_profiles.jsonl')
    courses = load_jsonl('courses.jsonl')
    lab_ids, lab_docs, _, starts = build_docs(labs)
    course_ids, course_docs = course_documents(courses)
    model = SentenceTransformer('BAAI/bge-m3', device='cuda')
    model.half()
    encode = lambda docs: np.asarray(model.encode(docs, batch_size=32, normalize_embeddings=True,
                                                   show_progress_bar=False), dtype=np.float32)
    lab_vectors = encode(lab_docs)
    course_vectors = encode(course_docs)
    key = hashlib.sha256(('bge-m3-cuda\n' + '\n'.join(lab_docs)).encode()).hexdigest()
    np.savez_compressed('doc_embeddings.npz', key=key, D=lab_vectors,
                        course_ids=np.asarray(course_ids), course_vectors=course_vectors,
                        lab_ids=np.asarray(lab_ids), lab_starts=np.asarray(starts))

    # Similarity is a ranking hint, never proof of a prerequisite or a lab/course relationship.
    sims = lab_vectors @ course_vectors.T
    ends = starts[1:] + [len(lab_docs)]
    links = {}
    for lid, begin, end in zip(lab_ids, starts, ends):
        row = sims[begin:end].max(axis=0)
        best = np.argsort(-row)[:20]
        links[lid] = {course_ids[i]: round(float(row[i]), 5) for i in best}
    sources = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
               for name in ('app_profiles.jsonl', 'courses.jsonl')}
    Path('lab_course_bge_m3.json').write_text(json.dumps({'model': 'BAAI/bge-m3', 'sources': sources, 'labs': links},
                                                         ensure_ascii=False), encoding='utf-8')
    print(f'Precomputed {len(lab_ids)} labs/{len(lab_docs)} texts and {len(course_ids)} courses.')


if __name__ == '__main__':
    main()
