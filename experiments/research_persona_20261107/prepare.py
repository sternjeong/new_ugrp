"""Build cases, the current-guide baseline (A), the scored paper selection (RS) and OpenAlex citing works (RSO).

Run: PYTHONPATH=. python3 experiments/research_persona_20261107/prepare.py
Generators only see papers up to 2024; 2025+ papers are kept for the judges and the time-split metric.
"""
import hashlib
import json
import math
import re
import time
import urllib.request
from pathlib import Path

from curri.curated_catalog import COMMON_FRACTION, CuratedCatalog, clip, content_words, course_lines, search_terms

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = ROOT / 'data' / 'sunwoo'
CUTOFF = 2024
CORE = ['MATH101', 'MATH102', 'PHYS101', 'CHEM101', 'CSED101']
LABS = [
    ('조민수', '로봇이 카메라로 주변 물체를 알아보고 직접 집는 게 신기해요. 컴퓨터 비전이랑 로봇을 같이 해보고 싶어요.',
     ['CSED233', 'MATH203', 'CSED343', 'CSED331'], ['CHEM221', 'LIFE319', 'LIFE321', 'CHEB308']),
    ('채수용', '전기차나 태양광에서 전력을 효율적으로 바꾸는 장치가 궁금해요. 회로를 직접 만들고 제어해보고 싶어요.',
     ['EECE231', 'EECE233', 'EECE320', 'EECE372'], ['LIFE319', 'LIFE321', 'CHEM221', 'CHEM222']),
    ('김준원', '아주 작은 센서나 칩 위에서 액체를 다루는 장치를 만들어보고 싶어요. 의료 진단에도 쓰인다고 들었어요.',
     ['MECH240', 'MECH250', 'MECH370', 'MATH200'], ['CSED233', 'CSED312', 'CSED331', 'MATH230']),
    ('정규열', '미생물 유전자를 설계해서 원하는 물질을 만들게 하는 연구가 궁금해요. 실험도 좋고 설계 도구도 관심 있어요.',
     ['LIFE319', 'LIFE321', 'CHEB308', 'CHEM221'], ['EECE231', 'EECE233', 'EECE372', 'MECH211']),
    ('김용태', '배터리나 수전해처럼 전기화학 에너지 소재가 궁금해요. 오래가는 전극을 만드는 연구를 해보고 싶어요.',
     ['AMSE205', 'CHEM211', 'CHEM221', 'AMSE414'], ['CSED233', 'CSED331', 'CSED312', 'EECE233']),
    ('이길호', '그래핀이나 초전도체 같은 양자 소자를 직접 만들어서 측정해보고 싶어요. 양자역학 수업이 재밌었어요.',
     ['PHYS201', 'PHYS206', 'PHYS301', 'PHYS401'], ['LIFE319', 'LIFE321', 'CHEB308', 'MECH211']),
]


GENERIC = set("""then than there their these those three four five first second also very much many more most each
other such into onto over under within without between among about above below after before during while where which
whose what when been being were have having does done make made makes making used uses using show shows shown showed
found find finds well good high higher highest low lower lowest large larger small smaller new novel recent recently
standard example examples include includes including included introduced introduce discussion discussed eventually ever
precisely respect useful tool tools like only both either neither same different various several further thus hence
however therefore although though because since overall total real ones work works study studies paper papers result
results present presents presented propose proposed proposes demonstrate demonstrated approach approaches method methods
performance effect effects based level levels case cases type types value values number numbers order range form forms
rate rates time times term terms part parts point points process processes structure structures property properties
information relationship space unit units output input detail details sets matter physic chemical mixed improve
improved improvement experimental computation module flow source image shape pattern procedure rigid linear basis practice""".split())


def course_brief(course):
    lines = course_lines(course)
    return {'code': course['code'], 'title': course['title'], 'intro': [clip(x, 160) for x in lines[:3]]}


def paper_text(p):
    return f"{p['title']} {p.get('abstract') or ''}"


def openalex_citing(work_id):
    url = ('https://api.openalex.org/works?' + f'filter=cites:{work_id}&sort=publication_date:desc&per-page=5'
           '&select=id,title,publication_year,abstract_inverted_index')
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'curri-research-experiment'}), timeout=30) as r:
        rows = json.loads(r.read())['results']
    out = []
    for row in rows:
        inv = row.get('abstract_inverted_index') or {}
        words = sorted(((i, w) for w, idx in inv.items() for i in idx))
        out.append({'id': row['id'].rsplit('/', 1)[-1], 'title': row.get('title') or '', 'year': row.get('publication_year'),
                    'abstract': clip(' '.join(w for _, w in words), 400)})
    return out


def main():
    catalog = CuratedCatalog(DATA)
    df, total = catalog._lab_word_df(), len(catalog.profiles)
    idf = lambda w: math.log((total + 1) / (df.get(w, 0) + 1))
    informative = lambda words: {w for w in words if df.get(w, 0) <= total * COMMON_FRACTION and w not in GENERIC and not w.isdigit()}
    papers = {row['id']: [p for p in row['papers'] if p.get('abstract') and len(p['abstract']) > 300 and p.get('year')]
              for row in map(json.loads, filter(str.strip, (DATA / 'papers.jsonl').read_text(encoding='utf-8').splitlines()))}
    cache_path = OUT / 'openalex_citing.json'
    citing_cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    cases = []
    for professor, query, fit, misfit in LABS:
        lid = next(l for l, p in catalog.profiles.items() if p['professors'][0] == professor)
        profile = catalog.profiles[lid]
        overview = catalog.overview(profile)
        intro = next((t['quote'] for t in profile['topics'] if t['section'] == 'research_intro'), '')
        sources = [{'id': f'S{i + 1}', 'kind': '연구 분야', 'text': item} for i, item in enumerate(overview['items'][:10])]
        if intro:
            sources.append({'id': f'S{len(sources) + 1}', 'kind': '연구실 소개', 'text': clip(intro, 900)})
        all_papers = sorted(papers.get(lid, []), key=lambda p: p.get('date') or str(p['year']), reverse=True)
        old = [p for p in all_papers if p['year'] <= CUTOFF]
        new = [p for p in all_papers if p['year'] > CUTOFF]
        old_rows = [{'id': f'P{i + 1}', 'openalex': p['openalex_id'], 'title': p['title'], 'year': p['year'],
                     'abstract': p['abstract']} for i, p in enumerate(old[:8])]
        detail = catalog.detail(lid)
        for condition, major in (('fit', fit), ('misfit', misfit)):
            taken = [catalog.course_map[c] for c in CORE + major]
            taken_words = informative(set().union(*[content_words(' '.join(course_lines(c)) + ' ' + c['title']) for c in taken]))
            variants = [v for vs in search_terms(query).values() for v in vs]
            scored = []
            for row in old_rows:
                text = re.sub(r'\s+', '', paper_text(row).lower())
                words = informative(content_words(paper_text(row)))
                interest = sum(v in text for v in variants) / max(1, len(variants))
                shared = sorted(words & taken_words, key=idf, reverse=True)
                coverage = sum(idf(w) for w in shared)
                gaps = sorted(words - taken_words, key=idf, reverse=True)[:6]
                scored.append({'paper': row, 'interest': interest, 'coverage': coverage, 'recency': (row['year'] - 2018) / (CUTOFF - 2018),
                               'shared': shared[:6], 'gaps': gaps})
            top = lambda key: max([s[key] for s in scored] + [1e-9])
            for s in scored:
                s['score'] = round(0.5 * s['interest'] / top('interest') + 0.35 * s['coverage'] / top('coverage')
                                   + 0.15 * max(0.0, s['recency']), 3)
            selection = sorted(scored, key=lambda s: -s['score'])[:3]
            first = selection[0]['paper']['openalex']
            if first not in citing_cache:
                citing_cache[first] = openalex_citing(first)
                time.sleep(0.5)
            taken_codes = {c['code'] for c in taken}
            candidates = [course_brief(catalog.course_map[c['code']]) for c in detail['courses'] if c['code'] not in taken_codes]
            selected_related = [c['code'] for c in detail['courses'] if c['code'] in taken_codes]
            guide = catalog.guide(lid, selected_related)
            cases.append({
                'id': f'{professor}_{condition}', 'lab_id': lid, 'condition': condition, 'professor': professor,
                'department': profile['department'], 'lab_name': profile['lab_name'], 'query': query,
                'transcript': [course_brief(c) for c in taken], 'profile_sources': sources, 'papers': old_rows[:5],
                'rs_selection': [{'paper': s['paper'], 'score': s['score'], 'interest': round(s['interest'], 3),
                                  'coverage': round(s['coverage'], 2), 'shared_concepts': s['shared'],
                                  'concepts_not_in_transcript': s['gaps']} for s in selection],
                'openalex_citing': citing_cache[first], 'candidate_courses': candidates,
                'baseline_guide': guide,
                'judge_lab': {'areas': overview['items'], 'intro': clip(intro, 900),
                              'papers': [{'title': p['title'], 'year': p['year'], 'abstract': clip(p['abstract'], 380)}
                                         for p in all_papers[:12]]},
                'future_papers': [{'title': p['title'], 'year': p['year'], 'abstract': p['abstract']} for p in new],
            })
    cache_path.write_text(json.dumps(citing_cache, ensure_ascii=False, indent=1))
    pool = {}
    for lid, rows in papers.items():
        new = [p for p in rows if p['year'] > CUTOFF]
        old = [p for p in rows if p['year'] <= CUTOFF]
        if len(new) >= 3 and len(old) >= 4 and lid in catalog.profiles:
            pool[lid] = sorted(content_words(' '.join(paper_text(p) for p in new)))
    (OUT / 'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=1))
    (OUT / 'future_pool.json').write_text(json.dumps(pool, ensure_ascii=False))
    files = [DATA / n for n in ('app_profiles.jsonl', 'courses.jsonl', 'papers.jsonl', 'labs.jsonl')] + [OUT / 'cases.json']
    (OUT / 'manifest.json').write_text(json.dumps({str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}, indent=1))
    print('cases', len(cases), 'future pool labs', len(pool))
    for c in cases:
        print(c['id'], 'related taken:', [x for x in c['baseline_guide']['selected_courses']] and len(c['baseline_guide']['selected_courses']),
              '| RS top:', [(s['paper']['id'], s['score'], s['shared_concepts'][:3]) for s in c['rs_selection']])


if __name__ == '__main__':
    main()
