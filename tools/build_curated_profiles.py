"""Derive source-backed app profiles exclusively from the curated sunwoo files."""
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / 'data' / 'sunwoo'


def rows(name):
    with (ROOT / name).open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def topic(label, quote, url, section, index):
    label = str(label or '').strip()
    quote = str(quote or '').strip()
    if not label or not quote:
        return None
    return {'concept': f'topic_{index}', 'concept_ko': label[:100], 'label_ko': label[:100],
            'quote': quote[:1200], 'source_urls': [url] if url else [],
            'section': section, 'role': 'domain', 'weight': 'primary', 'scope': 'core'}


def build():
    papers = {row['id']: row for row in rows('papers.jsonl')}
    profiles = []
    for row in rows('labs.jsonl'):
        if not row.get('recommendable'):
            continue
        lid = row['id']
        lab = row.get('lab') or {}
        intro = row.get('intro') or {}
        url = lab.get('url') or intro.get('source_url') or ''
        labels = []
        for area in row.get('research_areas') or []:
            label = area.get('name_ko') or area.get('name_en') or area.get('name')
            if label and label not in labels:
                labels.append(label)
        paper_row = papers.get(lid, {})
        for label in paper_row.get('core_topics') or []:
            if label and label not in labels:
                labels.append(label)
        topics = []
        for label in labels[:8]:
            item = topic(label, label, url, 'research_area', len(topics))
            if item:
                topics.append(item)
        for paper in (paper_row.get('papers') or [])[:5]:
            title = paper.get('title') or ''
            excerpt = title + ('. ' + paper['abstract'][:700] if paper.get('abstract') else '')
            paper_url = ('https://doi.org/' + paper['doi']) if paper.get('doi') else url
            item = topic(title, excerpt, paper_url, 'representative_paper', len(topics))
            if item:
                topics.append(item)
        intro_text = (intro.get('text') or '').strip()
        if intro_text and not intro.get('noise'):
            item = topic(lab.get('name') or '연구 소개', intro_text[:1000], intro.get('source_url') or url,
                         'research_intro', len(topics))
            if item:
                topics.append(item)
        summary = intro_text[:280] if intro_text and not intro.get('noise') else ' · '.join(labels[:3])
        profiles.append({'lab_id': lid, 'professors': [row['professor']['name_ko'] or row['professor'].get('name_en')],
                         'department': ' · '.join(row['professor'].get('departments') or []),
                         'lab_name': lab.get('name') or '', 'lab_url': url,
                         'status': 'ok' if topics else 'thin', 'summary_ko': summary,
                         'topics': topics, 'review_status': row.get('status'),
                         'paper_basis': paper_row.get('basis')})
    output = ROOT / 'app_profiles.jsonl'
    output.write_text(''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in profiles), encoding='utf-8')
    print(f'{len(profiles)} profiles, sha256={hashlib.sha256(output.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    build()
