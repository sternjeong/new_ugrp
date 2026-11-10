"""Make the chunk files the worker's query analysis needs from the vectorRAG pack (feat/proto: data/rag/pack300-whole).

Keeps lab chunks only and drops papers flagged as a namesake's (data/sunwoo/suspect_papers.json).
Run: python3 tools/embed_worker/build_search_assets.py <chunks.jsonl> <vectors.f32> <out_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LAB_KINDS = {'profile', 'intro', 'paper'}


def main(chunks_path, vectors_path, out_dir):
    chunks = [json.loads(line) for line in open(chunks_path, encoding='utf-8') if line.strip()]
    vectors = np.fromfile(vectors_path, dtype='<f4').reshape(len(chunks), -1)
    suspect = {p['openalex_id'] for papers in json.loads((ROOT / 'data/sunwoo/suspect_papers.json').read_text(encoding='utf-8'))['labs'].values() for p in papers}
    keep = [i for i, c in enumerate(chunks) if c['kind'] in LAB_KINDS and c['meta'].get('openalex_id') not in suspect]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'search_chunks.jsonl', 'w', encoding='utf-8') as stream:
        for i in keep:
            stream.write(json.dumps({'owner': chunks[i]['owner'], 'text': f"{chunks[i]['header']}\n{chunks[i]['text']}"}, ensure_ascii=False) + '\n')
    np.save(out / 'search_vectors.npy', vectors[keep])
    print(f'chunks {len(keep)} of {len(chunks)}, dropped as namesake papers {sum(chunks[i].get("kind") in LAB_KINDS for i in range(len(chunks))) - len(keep)}')


if __name__ == '__main__':
    main(*sys.argv[1:])
