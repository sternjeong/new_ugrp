"""Kaggle packet: chunks, lab documents, every phrase the strategies need and the reranker queries.

Run from the repo root: PYTHONPATH=.:experiments/engine_strategies_20261109 python3 experiments/engine_strategies_20261109/prepare.py <proto_dir> <packet_dir>
"""
import json
import sys
from pathlib import Path

from common import OUT, rule_parse
from tools.embed_worker.worker import build_docs, load_jsonl

ROOT = OUT.parents[1]
proto, packet_dir = Path(sys.argv[1]), Path(sys.argv[2])
queries = json.loads((OUT / 'queries.json').read_text())
llm = json.loads((OUT / 'llm_parse.json').read_text())
doc_phrases, chunk_phrases, rerank = set(), set(), {}
for q in queries:
    chunk_phrases.add(q['text'])                                  # V uses the raw text
    for clean in (False, True):
        p = rule_parse(q['text'], clean)
        if p['intent'] != 'search':
            continue
        doc_phrases |= set((p['likes'] or [p['norm']]) + p['dislikes'] + [p['norm']])
        if p['dislikes']:
            chunk_phrases |= {' '.join(p['likes'])} | set(p['dislikes'])
    L = llm[q['id']]
    if L['intent'] == 'search':
        chunk_phrases.add(L['search_text'])
        chunk_phrases |= set(L['dislikes'])
    rerank[q['id']] = [q['text']] + ([L['search_text']] if L['intent'] == 'search' else [])
chunks = load_jsonl(proto / 'data/rag/pack300-whole/chunks.jsonl')
lab_ids, docs, topic_of, starts = build_docs(load_jsonl(ROOT / 'data/sunwoo/app_profiles.jsonl'))
packet_dir.mkdir(parents=True, exist_ok=True)
(packet_dir / 'packet.json').write_text(json.dumps({
    'chunks': [f"{c['header']}\n{c['text']}" for c in chunks], 'kinds': [c['kind'] for c in chunks], 'owners': [c['owner'] for c in chunks],
    'lab_ids': lab_ids, 'docs': docs, 'topic_of': topic_of, 'starts': starts,
    'doc_phrases': sorted(doc_phrases), 'chunk_phrases': sorted(chunk_phrases), 'rerank_queries': sorted({t for ts in rerank.values() for t in ts})}, ensure_ascii=False))
print(len(doc_phrases), 'doc phrases;', len(chunk_phrases), 'chunk phrases;', len({t for ts in rerank.values() for t in ts}), 'rerank queries')
