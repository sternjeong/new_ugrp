"""Packet for the Kaggle job: chunks, lab cards for Doc2Query, research vocabulary, every text to embed.

Run from the repo root: PYTHONPATH=.:experiments/no_llm_20261109:experiments/engine_strategies_20261109 python3 experiments/no_llm_20261109/prepare.py <proto_dir> <packet_dir>
"""
import json
import re
import sys
from pathlib import Path

from common import rule_parse
from curri.curated_catalog import CuratedCatalog, clip, load_jsonl
from forms import forms
from tools.embed_worker.worker import build_docs

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'experiments/engine_strategies_20261109'
proto, packet_dir = Path(sys.argv[1]), Path(sys.argv[2])
sets = {'dev': (json.loads((BASE / 'queries.json').read_text()), json.loads((BASE / 'llm_parse.json').read_text())),
        'test': (json.loads((HERE / 'holdout.json').read_text()), json.loads((HERE / 'llm_parse_holdout.json').read_text()))}
catalog = CuratedCatalog(ROOT / 'data/sunwoo')
papers = {r['id']: r['papers'] for r in load_jsonl(ROOT / 'data/sunwoo/papers.jsonl')}
suspect = catalog.suspect_titles

doc_phrases, dense_texts, retrieve_texts, translate = set(), set(), set(), set()
for queries, llm in sets.values():
    for q in queries:
        for clean in (False, True):
            p = rule_parse(q['text'], clean)
            if p['intent'] == 'search':
                doc_phrases |= set((p['likes'] or [p['norm']]) + p['dislikes'] + [p['norm']])
        parsed, positive = forms(q['text'])
        dense_texts |= {q['text'], positive} | set(parsed['dislikes'])
        translate |= {positive}
        L = llm[q['id']]
        if L['intent'] == 'search':
            dense_texts |= {L['search_text']} | set(L['dislikes'])
retrieve_texts = set(translate)


def strings():
    for row in load_jsonl(ROOT / 'data/sunwoo/labs.jsonl'):
        for area in row.get('research_areas') or []:
            yield area.get('name_ko')
            yield area.get('name_en')
    for profile in catalog.profiles.values():
        for t in profile['topics']:
            if t['section'] == 'research_area':
                yield t['label_ko']
    for row in papers.values():
        for p in row:
            yield p.get('subfield')
            yield p.get('topic')
            yield p.get('field')
    for c in catalog.courses:
        yield re.split(r'[:(（]', c['title'])[0]


vocab = sorted({s.strip() for s in strings() if s and 3 <= len(s.strip()) <= 60})


def lab_card(lid):
    p = catalog.profiles[lid]
    intro = next((t['quote'] for t in p['topics'] if t['section'] == 'research_intro'), '')
    kept = [x for x in papers.get(lid, []) if x.get('title') and x['title'] not in suspect.get(lid, ())]
    titles = [x['title'] for x in sorted(kept, key=lambda x: x.get('date') or str(x.get('year') or ''), reverse=True)[:6]]
    return {'lab_id': lid, 'text': json.dumps({'학과': p['department'], '연구 분야': catalog.overview(p)['items'][:10], '소개': clip(intro, 700), '최근 논문': titles}, ensure_ascii=False)}


exemplars = json.loads((HERE / 'intent_exemplars.json').read_text())
chunks = load_jsonl(proto / 'data/rag/pack300-whole/chunks.jsonl')
lab_ids, docs, topic_of, starts = build_docs(load_jsonl(ROOT / 'data/sunwoo/app_profiles.jsonl'))
packet_dir.mkdir(parents=True, exist_ok=True)
(packet_dir / 'packet.json').write_text(json.dumps({
    'chunks': [f"{c['header']}\n{c['text']}" for c in chunks], 'kinds': [c['kind'] for c in chunks], 'owners': [c['owner'] for c in chunks],
    'lab_ids': lab_ids, 'docs': docs, 'topic_of': topic_of, 'starts': starts, 'cards': [lab_card(l) for l in sorted(catalog.profiles)],
    'vocab': vocab, 'doc_phrases': sorted(doc_phrases), 'dense_texts': sorted(dense_texts), 'translate': sorted(translate),
    'retrieve_texts': sorted(retrieve_texts), 'exemplars': exemplars, 'all_queries': [q['text'] for qs, _ in sets.values() for q in qs]}, ensure_ascii=False))
print('vocab', len(vocab), 'doc', len(doc_phrases), 'dense', len(dense_texts), 'translate', len(translate), 'cards', len(catalog.profiles), 'chunks', len(chunks))
print(vocab[:5], vocab[-5:])
