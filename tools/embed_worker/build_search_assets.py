"""Make the chunk files the worker's query analysis needs from the vectorRAG pack (feat/proto: data/rag/pack300-whole).

Keeps lab chunks only and drops papers flagged as a namesake's (data/sunwoo/suspect_papers.json) and three kinds of
bad chunks (D1 from the teammate's engine-modules review, re-measured 2026-11-22): a second copy of the same text within a lab, project
write-ups whose `Advisor:` heading names another professor (shared project pages copied into three ML labs), and page
shells (under 40 characters, or mostly dates and news lines).
Run: python3 tools/embed_worker/build_search_assets.py <chunks.jsonl> <vectors.f32> <out_dir>
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
LAB_KINDS = {'profile', 'intro', 'paper'}
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


def main(chunks_path, vectors_path, out_dir):
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
    keep = [i for i in lab if i not in bad and chunks[i]['meta'].get('openalex_id') not in suspect]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'search_chunks.jsonl', 'w', encoding='utf-8') as stream:
        for i in keep:
            stream.write(json.dumps({'owner': chunks[i]['owner'], 'text': f"{chunks[i]['header']}\n{chunks[i]['text']}"}, ensure_ascii=False) + '\n')
    np.save(out / 'search_vectors.npy', vectors[keep])
    print(f'chunks {len(keep)} of {len(lab)} lab chunks; dropped namesake papers {len(namesake)}, '
          + ', '.join(f'{k} {v}' for k, v in sorted(Counter(bad.values()).items())))


if __name__ == '__main__':
    main(*sys.argv[1:])
