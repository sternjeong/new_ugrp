"""R5 reranking (engine-modules branch, docs/plans/2026-11-22-engine-modules.md): the first candidate labs are
judged again by a cross-encoder that reads the query and the lab's text together.

The first pass (bi-encoder) embeds query and chunk apart, so '딥러닝 이용한 의학 연구' can land on a chunk about
applying deep learning anywhere. A cross-encoder scores the pair at once. The model (bge-reranker-v2-m3) runs on
the embedding worker (tools/embed_worker/worker.py, op 'rerank'); this module builds the passage a lab is judged
on. If the worker does not answer, the first-pass order stays.
"""
import re

TOP = 50          # candidates rescored (after folding co-led labs). 2026-11-26, 128 graded queries: nDCG@10 20: 0.723,
                  # 30: 0.748, 50: 0.764 (50 vs 30 +0.016 [+0.005, +0.029]). Of the core labs (grade 2) missing from
                  # the top 10, 39 of 63 were outside the first 20 and 11 of 42 outside the first 50.
                  # M1 Pro MPS: 3.8 / 6.5 / 14.9 s per search, so tools/local_mac uses 30.
CHUNK_CHARS = 450  # per chunk in a lab's passage
CHUNKS = 3        # best distinct chunks per lab
DISLIKE = 0.15    # probability taken off per unit of the disliked phrase's z-score above average


def clip(text, n):
    text = re.sub(r'\s+', ' ', text or '').strip()
    return text if len(text) <= n else text[:n].rsplit(' ', 1)[0] + '…'


def passage(profile, chunks, n=CHUNKS, chars=CHUNK_CHARS):
    """What the cross-encoder reads for one lab: name, professors, department, research areas, the lab summary
    (R2) when it matched, then its best intro and paper chunks for this query."""
    head = ' · '.join(x for x in (profile.get('lab_name'), ', '.join(profile.get('professors') or []), profile.get('department')) if x)
    areas = ', '.join(t.get('label_ko') or t.get('label') or '' for t in (profile.get('topics') or [])[:8])
    lines = [head] + ([f'연구 분야: {areas}'] if areas else [])
    seen = set()
    summary = next((c for _, c in chunks if c['kind'] == 'summary'), None)
    if summary is not None:
        lines.append(clip(summary['text'], chars * 2))
    for _, c in sorted(chunks, key=lambda x: -x[0]):
        if c['kind'] not in ('intro', 'paper') or c['id'] in seen:
            continue
        seen.add(c['id'])
        lines.append(clip(c['text'], chars))
        if len(seen) == n:
            break
    return '\n'.join(lines)
