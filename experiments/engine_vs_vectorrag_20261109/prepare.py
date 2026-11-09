"""Build the query set and the Kaggle packet (teammate's chunks, our lab documents, query texts and phrases).

Run from the repo root: PYTHONPATH=. python3 experiments/engine_vs_vectorrag_20261109/prepare.py <proto_dir> <packet_dir>
"""
import json
import sys
from pathlib import Path

from curri.curated_query_engine import classify_curated_query
from tools.embed_worker.worker import build_docs, load_jsonl

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
proto, packet_dir = Path(sys.argv[1]), Path(sys.argv[2])
MINE = [('m1', '로봇은 싫고 생체 신호 분석이 좋아요'), ('m2', '반도체 소자보다 의료 로봇이 좋아요'), ('m3', '배터리 소재의 수명과 열화를 연구하고 싶어요'),
        ('m4', '양자컴퓨터 연구를 하고 싶어요'), ('m5', '의료 영상에서 종양을 찾고 싶어요'), ('m6', '컴퓨터 구조가 재밌어요'), ('m7', '화학은 별로고 신약 개발이 궁금해요'),
        ('m8', '기후 변화와 탄소 포집 연구'), ('m9', '고분자 합성 연구를 하고 싶어요'), ('m10', '전자회로는 싫고 뇌과학이 좋아요')]

gold = load_jsonl(proto / 'data/eval/advisor_queries.jsonl')
queries = []
for i, q in enumerate(gold):
    queries.append({'id': q['id'], 'group': 'T', 'text': q['query'], 'panel': i < 12, 'relevant': [r['id'] for r in q['relevant']]})
queries += [{'id': i, 'group': 'M', 'text': t, 'panel': True} for i, t in MINE]
queries += [{'id': f'b{n + 1}', 'group': 'B', 'type': q['type'], 'text': q['text'], 'panel': True}
            for n, q in enumerate(json.loads((OUT / 'queries_blind.json').read_text()))]
phrases = []
for q in queries:
    parsed = classify_curated_query(q['text'])
    q['intent'] = parsed['intent']
    if parsed['intent'] == 'search':
        q['phrases'] = list(dict.fromkeys((parsed['likes'] or [parsed['norm']]) + parsed['dislikes'] + [parsed['norm']]))
        phrases += q['phrases']
(OUT / 'queries.json').write_text(json.dumps(queries, ensure_ascii=False, indent=1))

chunks = load_jsonl(proto / 'data/rag/pack300-whole/chunks.jsonl')
lab_ids, docs, topic_of, starts = build_docs(load_jsonl(ROOT / 'data/sunwoo/app_profiles.jsonl'))
packet_dir.mkdir(parents=True, exist_ok=True)
(packet_dir / 'packet.json').write_text(json.dumps({
    'chunks': [f"{c['header']}\n{c['text']}" for c in chunks], 'lab_ids': lab_ids, 'docs': docs, 'topic_of': topic_of, 'starts': starts,
    'queries': [q['text'] for q in queries], 'phrases': sorted(set(phrases))}, ensure_ascii=False))
print(len(queries), 'queries,', sum(q['panel'] for q in queries), 'panel;', len(chunks), 'chunks;', len(docs), 'docs;', len(set(phrases)), 'phrases')
print('non-search intents:', [(q['id'], q['intent']) for q in queries if q['intent'] != 'search'])
