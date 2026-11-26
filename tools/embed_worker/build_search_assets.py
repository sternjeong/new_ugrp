"""Make the chunk files the worker's query analysis needs from the vectorRAG pack (feat/proto: data/rag/pack300-whole).

Keeps lab chunks only and drops papers flagged as a namesake's (data/sunwoo/suspect_papers.json), papers the lab no
longer shows after a reviewed paper decision (not in the lab's bundle of data/sunwoo/papers.jsonl: the pack was cut
before the review, see docs/analysis/PAPER_ATTRIBUTION_REVIEW.md) and three kinds of
bad chunks (D1 from the teammate's engine-modules review, re-measured 2026-11-22): a second copy of the same text within a lab, project
write-ups whose `Advisor:` heading names another professor (shared project pages copied into three ML labs), and page
shells (under 40 characters, or mostly dates and news lines).
With a fourth argument, the lab summaries (R2 from the teammate's engine modules: data/sunwoo/lab_summaries, one
Korean summary per lab written by Claude Haiku with engine/modules' tools/build_lab_summaries.py from final's reviewed
papers on 2026-11-26 and embedded with the same Ollama BGE-M3) join each lab's chunks, so a lab whose material is a
list of titles still has a passage that says what it studies. Rerun that tool when a lab's papers or intro change.
The server gets the same chunks without vectors in data/sunwoo/search_chunks.jsonl: the search engine
(curri/curated_query_engine.py RagQueryEngine) quotes them as a card's evidence and builds the reranker's passage.
Run: python3 tools/embed_worker/build_search_assets.py <chunks.jsonl> <vectors.f32> <out_dir> [data/sunwoo/lab_summaries]
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB_KINDS = {'profile', 'intro', 'paper'}
SERVER_CHUNKS = ROOT / 'data/sunwoo/search_chunks.jsonl'  # the same chunks without vectors, for the server's cards
ADVISOR = re.compile(r'Advisor\s*:\s*([A-Za-z .\-]+)')
DATE_LINE = re.compile(r'[A-Z][a-z]{2}\.?|\d{4}|\d{4}[.\-/]\d{1,2}([.\-/]\d{1,2})?')
NEWS_LINE = re.compile(r'accepted to|awarded|has been selected|won the|best paper award', re.I)


def letters(name):
    return re.sub(r'[^a-z]', '', (name or '').lower())


def bad_chunks(chunks, english_names):
    """Index -> reason for chunks that should not stand for their lab in search."""
    bad, seen = {}, defaultdict(set)
    owner, advisor = None, None
    for i, c in enumerate(chunks):
        if c['kind'] not in LAB_KINDS:
            continue
        body = c['text'].strip()
        key = re.sub(r'\s+', ' ', body)
        if key in seen[c['owner']]:
            bad[i] = 'duplicate'
        seen[c['owner']].add(key)
        if c['kind'] != 'intro':
            owner, advisor = None, None
            continue
        if c['owner'] != owner:
            owner, advisor = c['owner'], None
        # An Advisor heading holds for the chunks after it until the next heading.
        for line in body.split('\n'):
            if line.startswith('#'):
                m = ADVISOR.search(line)
                advisor = letters(m.group(1)) if m else None
        name = english_names.get(c['owner'], '')
        if advisor and advisor not in {letters(name), letters(' '.join(reversed(name.split())))}:
            bad.setdefault(i, 'other_advisor')
        lines = [line.strip() for line in body.split('\n') if line.strip()]
        shell = sum(bool(DATE_LINE.fullmatch(line)) or bool(NEWS_LINE.search(line)) for line in lines)
        if len(body) < 40 or (lines and shell / len(lines) >= 0.6):
            bad.setdefault(i, 'page_shell')
    return bad


def removed_papers(chunks, current):
    """Indexes of paper chunks whose paper is no longer among the owner's papers. `current` is {lab_id: paper ids,
    versions included}. A lab that is missing from papers.jsonl is left alone."""
    return [i for i, c in enumerate(chunks)
            if c['kind'] == 'paper' and c['owner'] in current and (c.get('meta') or {}).get('openalex_id')
            and c['meta']['openalex_id'].rsplit('/', 1)[-1] not in current[c['owner']]]


def current_papers(path):
    current = {}
    for line in open(path, encoding='utf-8'):
        row = json.loads(line)
        current[row['id']] = {i for p in row.get('papers') or [] for i in (p.get('openalex_id'), *(p.get('versions') or [])) if i}
    return current


def summary_rows(chunks, labs):
    """Indexes of the summary chunks to keep: one per lab the app still lists, the last when a lab has two."""
    last = {c['owner']: i for i, c in enumerate(chunks) if c.get('kind') == 'summary' and c['owner'] in labs}
    return sorted(last.values())


def main(chunks_path, vectors_path, out_dir, summaries_dir=None):
    import numpy as np  # only the build needs it; the chunk rules above are tested without it
    chunks = [json.loads(line) for line in open(chunks_path, encoding='utf-8') if line.strip()]
    vectors = np.fromfile(vectors_path, dtype='<f4').reshape(len(chunks), -1)
    suspect = {p['openalex_id'] for papers in json.loads((ROOT / 'data/sunwoo/suspect_papers.json').read_text(encoding='utf-8'))['labs'].values() for p in papers}
    english = {}
    for line in open(ROOT / 'data/sunwoo/labs.jsonl', encoding='utf-8'):
        row = json.loads(line)
        english[row['id']] = (row.get('professor') or {}).get('name_en') or ''
    bad = bad_chunks(chunks, english)
    lab = [i for i, c in enumerate(chunks) if c['kind'] in LAB_KINDS]
    namesake = [i for i in lab if chunks[i]['meta'].get('openalex_id') in suspect]
    removed = set(removed_papers(chunks, current_papers(ROOT / 'data/sunwoo/papers.jsonl')))
    keep = [i for i in lab if i not in bad and i not in removed and chunks[i]['meta'].get('openalex_id') not in suspect]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [{'id': chunks[i]['id'], 'owner': chunks[i]['owner'], 'kind': chunks[i]['kind'], 'text': f"{chunks[i]['header']}\n{chunks[i]['text']}"} for i in keep]
    table = [chunks[i] for i in keep]  # the server's copy: cards quote these chunks as evidence
    kept = vectors[keep]
    if summaries_dir:
        folder = Path(summaries_dir)
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        pack = json.loads((Path(chunks_path).parent / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('embedder') != pack.get('embedder'):
            raise SystemExit(f"summaries embedded with {manifest.get('embedder')}, chunks with {pack.get('embedder')}")
        summaries = [json.loads(line) for line in open(folder / 'chunks.jsonl', encoding='utf-8') if line.strip()]
        summary_vectors = np.fromfile(folder / 'vectors.f32', dtype='<f4').reshape(len(summaries), -1)
        take = summary_rows(summaries, set(english))
        rows += [{'id': summaries[i]['id'], 'owner': summaries[i]['owner'], 'kind': 'summary', 'text': f"{summaries[i]['header']}\n{summaries[i]['text']}"} for i in take]
        table += [summaries[i] for i in take]
        kept = np.concatenate([kept, summary_vectors[take]])
        print(f'lab summaries {len(take)} of {len(summaries)}')
    with open(out / 'search_chunks.jsonl', 'w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    np.save(out / 'search_vectors.npy', kept)
    with open(SERVER_CHUNKS, 'w', encoding='utf-8') as stream:
        for c in table:
            stream.write(json.dumps({k: c[k] for k in ('id', 'owner', 'kind', 'text', 'meta')}, ensure_ascii=False) + '\n')
    print(f'chunks {len(keep)} of {len(lab)} lab chunks; dropped namesake papers {len(namesake)}, papers removed by review {len(removed)}, '
          + ', '.join(f'{k} {v}' for k, v in sorted(Counter(bad.values()).items())))


if __name__ == '__main__':
    main(*sys.argv[1:])
