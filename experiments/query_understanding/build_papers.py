"""팀원 카탈로그 페이지(HTML)의 lab-data JSON에서 앱 연구실 교수의 대표 논문만 뽑아 papers_app.jsonl로 저장한다.
사용: python3 -I build_papers.py <catalog.html> <repo_root>
교수 매칭: 한글 이름 → 여러 레코드면 영문 이름(pf.en) 일치로 선택. 매칭 못 하면 건너뛰고 출력한다."""
import sys, re, json
html, root = sys.argv[1], sys.argv[2]
rows = json.loads(re.search(r'<script id="lab-data" type="application/json">(.*?)</script>', open(html, encoding='utf-8').read(), re.S).group(1))['rows']
out, skipped = [], []
for line in open(f'{root}/data/lab_profiles.jsonl', encoding='utf-8'):
    p = json.loads(line)
    if p['status'] == 'insufficient':
        continue
    for prof in p['professors']:
        m = re.match(r'(.+?)\s*\((.+)\)', prof)
        name, en = (m.group(1), m.group(2)) if m else (prof, None)
        cand = [r for r in rows if r['pf'] and r['pf'].get('n') == name]
        if len(cand) > 1 and en:
            cand = [r for r in cand if (r['pf'].get('en') or '').lower() == en.lower()] or cand
        if len(cand) != 1:
            skipped.append((prof, len(cand)))
            continue
        for q in cand[0].get('rp', []):
            out.append({'lab_id': p['lab_id'], 'professor': name, 'title': q['t'], 'year': q['y'], 'abstract': q.get('a') or '', 'doi': q.get('doi')})
with open('papers_app.jsonl', 'w', encoding='utf-8') as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + '\n')
print('papers', len(out), 'labs', len({o['lab_id'] for o in out}), 'with abstract', sum(1 for o in out if o['abstract']), 'skipped', skipped)
