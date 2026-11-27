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
DISLIKE = 0.8     # a lab's probability is multiplied by 1 - DISLIKE x (the reranker's probability for the dislikes)
# Words around a topic that only say how the student feels or asks ('NeRF 같은 거 너무 멋있어 보여', '모터 구동 어디서 해'):
# the reranker read them as part of the query and gave the right labs probabilities under 0.005.
FILLER_WORDS = re.compile(r'^(?:같은|이런|그런|어디서?|뭔가|실제로|직접|정말|진짜|너무|되게|완전|좀|거|것|곳|데|쪽|게|건|걸|'
                          r'멋있\S*|신기\S*|재밌\S*|재미있\S*|좋\S*|싶\S*|있\S*|없\S*|하는|해\S*|하고\S*|보여\S*|보이\S*|만드는|연구하는|다루는)$')


def query(phrases):
    """The reranker's query: the phrases joined, without the words that carry no topic."""
    kept = []
    for phrase in phrases:
        words = [w for w in phrase.split() if not FILLER_WORDS.match(w)]
        kept.append(' '.join(words) or phrase)
    return ', '.join(dict.fromkeys(kept))


def clip(text, n):
    text = re.sub(r'\s+', ' ', text or '').strip()
    return text if len(text) <= n else text[:n].rsplit(' ', 1)[0] + '…'


def passage(profile, chunks, n=CHUNKS, chars=CHUNK_CHARS, summary=None):
    """What the cross-encoder reads for one lab: name, professors, department, research areas, the lab summary
    (R2) when it matched, then its best intro and paper chunks for this query."""
    head = ' · '.join(x for x in (profile.get('lab_name'), ', '.join(profile.get('professors') or []), profile.get('department')) if x)
    areas = ', '.join(t.get('label_ko') or t.get('label') or '' for t in (profile.get('topics') or [])[:8])
    lines = [head] + ([f'연구 분야: {areas}'] if areas else [])
    seen = set()
    summary = summary or next((c for _, c in chunks if c['kind'] == 'summary'), None)  # the lab's own summary, matched or not
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
