"""Tag courses with shared concepts. Title hit = strong; body needs a specific keyword hit."""
import json, re, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
concepts = json.load(open(ROOT/'data/concepts.json'))['concepts']
courses = [json.loads(l) for l in open(ROOT/'data/courses.jsonl')]

def pat(term):
    if re.fullmatch(r'[a-z0-9 .\-/]+', term):
        return re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', re.I)
    return re.compile(re.escape(term))
PATS = {c['id']: [(k, pat(k)) for k in c['keywords']] for c in concepts}
# keywords too generic to count alone in body text
WEAK = {'바이오', 'biology', 'biological', '생명', '제어', 'control', 'fet', 'ct', 'pet', 'rf', 'xr', 'soc', 'nano', '나노', '분자', 'molecular', 'cell biology', '세포', '결정', 'crystal', '재료', '소재', 'metal', '금속', '전파', '공정', 'simulation', '시뮬레이션', 'fem', '유한요소', 'neural', 'cognitive', '인지', '뇌', 'brain', '교육', 'education', '학습자', 'learner', '통계', '확률', 'statistics', 'probability', 'regression', '회귀분석', '프로그래밍', 'programming', '코딩', 'coding', '알고리즘', 'algorithm', '자료구조', 'data structure', 'logic', '논리학', '최적화', 'optimization', '데이터 분석', 'data analysis', '네트워크', '인터넷', 'internet', '보안', 'security', '회로', 'circuit', '아날로그', 'analog', '음성', 'speech', 'voice', '센싱', 'sensing', '카메라', 'camera', '발광', '광학', 'optics', 'optical', '반도체', 'semiconductor', 'sql', 'polymer', '고분자', 'thermodynamics', '열역학', 'cooling', '냉각', 'manufacturing', '제조', 'physiological signal', 'imaging system', 'microscopy', '현미경', 'electrode', '전극', 'gnn', 'gan', 'eda', 'hdl', 'ux', 'bci', 'hpc', 'llm', 'vla', 'slam', 'uav', 'thz', 'ssd', 'mri', 'npu', 'gpu', 'lidar', 'hmd', 'iot', 'p2p', 'tcp', 'ofdm', 'mimo', 'ldpc', 'dft', 'tcad'}

def excerpt(text, m, width=140):
    s = max(0, m.start()-60); e = min(len(text), m.end()+80)
    return text[s:e].replace('\n', ' ').strip()

rows = []
for c in courses:
    title = ((c.get('course_name_kr') or '') + ' ' + (c.get('course_name_en') or '')).strip()
    body = ' '.join((c.get(k) or '') for k in ('description', 'objectives'))
    plan = c.get('course_plan') or ''
    found = {}
    for cid, kws in PATS.items():
        hits_title = [k for k, p in kws if p.search(title)]
        hits_body = [k for k, p in kws if p.search(body)]
        hits_plan = [k for k, p in kws if p.search(plan)]
        strong_body = [k for k in hits_body if k not in WEAK]
        if hits_title:
            k = hits_title[0]; m = pat(k).search(title)
            found[cid] = {'strength': 'title', 'keywords': sorted(set(hits_title+hits_body)), 'evidence': title}
        elif strong_body or len(set(hits_body)) >= 2:
            k = (strong_body or hits_body)[0]; m = pat(k).search(body)
            found[cid] = {'strength': 'body', 'keywords': sorted(set(hits_body)), 'evidence': excerpt(body, m)}
        elif len(set(hits_plan)) >= 2 and [k for k in hits_plan if k not in WEAK]:
            k = [k for k in hits_plan if k not in WEAK][0]; m = pat(k).search(plan)
            found[cid] = {'strength': 'plan', 'keywords': sorted(set(hits_plan)), 'evidence': excerpt(plan, m)}
    rows.append({'record_id': c['record_id'], 'course_code': c['course_code'], 'name_kr': c.get('course_name_kr'), 'name_en': c.get('course_name_en'),
                 'concepts': [{'concept': cid, **v} for cid, v in found.items()], 'quality_flags': c.get('quality_flags', []),
                 'review_status': 'auto', 'tagged_by': 'keyword rules over concepts.json (2026-09-16)'})
with open(ROOT/'data/course_profiles.jsonl', 'w') as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False)+'\n')
n = collections.Counter(len(r['concepts']) for r in rows)
print('courses', len(rows), 'concepts per course', sorted(n.items()))
per = collections.Counter(x['concept'] for r in rows for x in r['concepts'])
print('courses per concept', per.most_common())
print('untagged', [f"{r['course_code']} {r['name_kr']}" for r in rows if not r['concepts']][:40])
