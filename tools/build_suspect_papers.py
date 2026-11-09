"""Flag papers that likely belong to a namesake of the lab's professor (OpenAlex author merges).

A paper is flagged only when all three hold: it is on neither the professor's own publication list nor affiliated with
POSTECH; its OpenAlex subfield matches none of the lab's verified papers; and its embedding is far from the centroid of
the lab's verified papers and introduction. Flagged papers are skipped in search evidence and the AI guide.

Usage: python3 tools/build_suspect_papers.py <chunks.jsonl of the vectorRAG index> <vectors.f32>  → data/sunwoo/suspect_papers.json
"""
import collections
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sunwoo'
THRESHOLD = 0.60
INTRO_ONLY_THRESHOLD = 0.50  # no verified paper to compare with, so only the lab's introduction anchors the check
# Read by hand: flagged by the rule, but on the professor's own topic (title prefixes).
GENUINE = ('A Case Study of a DRAM-NVM', 'Programmed Delay of a Virulence', 'Water-Supply Disaster', 'A Study on the Rainfall-Storage', 'Influence of Rainfall Patterns')
GENUINE_PROFESSORS = {'조철현', '김희찬'}  # no verified paper to compare with, but the flagged papers are their own field


def main():
    chunks = [json.loads(line) for line in open(sys.argv[1])]
    vectors = np.fromfile(sys.argv[2], dtype='<f4').reshape(len(chunks), -1)
    rows = {r['id']: r for r in map(json.loads, open(DATA / 'papers.jsonl'))}
    labs = {r['lab_id']: r for r in map(json.loads, open(DATA / 'app_profiles.jsonl'))}
    by_lab = collections.defaultdict(list)
    for i, c in enumerate(chunks):
        if c['kind'] in ('paper', 'intro', 'profile') and c['owner'] in labs:
            by_lab[c['owner']].append(i)
    out, checked = {}, 0
    for lid, ids in by_lab.items():
        papers = {p['title']: p for p in rows.get(lid, {}).get('papers', [])}
        lookup = lambda i: next((p for t, p in papers.items() if chunks[i]['text'].startswith(t[:60])), None)
        verified = [i for i in ids if chunks[i]['kind'] == 'paper' and (lookup(i) or {}).get('in_list') or chunks[i]['kind'] == 'paper' and (lookup(i) or {}).get('postech_affiliation')]
        fields = {lookup(i).get('subfield') for i in verified}
        anchors = verified + [i for i in ids if chunks[i]['kind'] == 'intro']
        if not anchors or labs[lid]['professors'][0] in GENUINE_PROFESSORS:
            continue
        centre = vectors[anchors].mean(0)
        centre /= np.linalg.norm(centre)
        for i in ids:
            p = lookup(i) if chunks[i]['kind'] == 'paper' else None
            if p is None or p.get('in_list') or p.get('postech_affiliation') or p.get('subfield') in fields:
                continue
            checked += 1
            similarity = float(vectors[i] @ centre)
            if similarity < (THRESHOLD if fields else INTRO_ONLY_THRESHOLD) and not p['title'].startswith(GENUINE):
                out.setdefault(lid, []).append({'title': p['title'], 'openalex_id': p.get('openalex_id'), 'subfield': p.get('subfield'), 'similarity': round(similarity, 3)})
    (DATA / 'suspect_papers.json').write_text(json.dumps({'_about': __doc__.strip().splitlines()[0], 'labs': out}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{sum(map(len, out.values()))}편 표시 ({len(out)}개 연구실, 후보 {checked}편 점검)')


if __name__ == '__main__':
    main()
