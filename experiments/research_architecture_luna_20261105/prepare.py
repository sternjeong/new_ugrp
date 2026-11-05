import json
from pathlib import Path
from curri.curated_catalog import CuratedCatalog

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
old=json.loads((root/'experiments/research_topic_generation_20261105/cases.json').read_text())
catalog=CuratedCatalog(root/'data/sunwoo')
chosen={'sensor_base':'EECE454','sensor_course':'DISU431','robot_base':'CSED343',
        'robot_course':'CSED515','chem_base':'CHEM221','chem_course':'CHEB469E'}
cases=[]
for x in old:
 if x['id'] not in chosen: continue
 course=catalog.course_map[chosen[x['id']]]
 assert course['code'] in {c['id'] for c in catalog.detail(x['lab_id'])['courses']}
 cases.append({**x,'courses':[{'id':course['code'],'title':course['title'],
                'description':(course.get('description') or '')[:1200],
                'plan':(course.get('lecture_plan') or '')[:1200]}]})
(out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
baseline=[]
for c in cases:
 g=catalog.guide(c['lab_id'],[x['id'] for x in c['courses']])
 # Render the content actually presented to the user, including both columns.
 lines=['수강 표시: '+', '.join(x['name'] for x in g['selected_courses'])]
 for label,key in [('지금 시작할 탐색','start_now'),('추가 준비','prepare_next')]:
  for t in g[key]:
   lines.append(label+' | '+t['title']+' | '+t['basis']+' | '+' '.join(t['steps'])+
                ' | 참고 과목: '+', '.join(x['name'] for x in t['courses'])+
                ' | 연구실 원문: '+'; '.join(e.get('text','') for e in t['evidence']))
 baseline.append({'case_id':c['id'],'text':'\n'.join(lines)})
(out/'baseline.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2))
print('cases',len(cases))
