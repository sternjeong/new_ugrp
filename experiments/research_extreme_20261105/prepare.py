"""Freeze evidence and generate the actual A and a source-limited rule baseline."""
import json,re
from pathlib import Path
from curri.curated_catalog import CuratedCatalog

ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
catalog=CuratedCatalog(ROOT/'data/sunwoo')
labs={r['id']:r for r in map(json.loads,(ROOT/'data/sunwoo/labs.jsonl').read_text().splitlines())}
papers={r['id']:r['papers'] for r in map(json.loads,(ROOT/'data/sunwoo/papers.jsonl').read_text().splitlines())}
scenarios=json.loads((OUT/'scenarios.json').read_text())['cases']
assert len(scenarios)==12 and len({s['lab_id'] for s in scenarios})==12
cases=[]
for i,s in enumerate(scenarios):
 lid=s['lab_id']; offered={c['id'] for c in catalog.detail(lid)['courses']}
 p=next(p for p in papers[lid] if p['openalex_id']==s['paper_openalex_id'])
 assert p.get('abstract') and len(s['courses'])==2 and all(c['code'] in offered for c in s['courses'])
 def course(code):
  c=catalog.course_map[code]
  return {'id':code,'title':c['title'],'description':(c.get('description') or '')[:1800],
          'plan':(c.get('lecture_plan') or '')[:1800],
          'description_truncated':len(c.get('description') or '')>1800,
          'plan_truncated':len(c.get('lecture_plan') or '')>1800}
 variants=[('course1',s['interest_sentences'][0],[course(s['courses'][0]['code'])]),
           ('course2',s['interest_sentences'][0],[course(s['courses'][1]['code'])])]
 if i<4:
  variants += [('interest',s['interest_sentences'][1],[course(s['courses'][0]['code'])]),
               ('none',s['interest_sentences'][0],[])]
 for name,interest,selected in variants:
  cases.append({'id':s['case_id']+'_'+name,'cluster':s['case_id'],'condition':name,'lab_id':lid,
                'department':catalog.profiles[lid]['department'],'professor':labs[lid]['professor']['name_ko'],
                'interest':interest,'paper':{'id':p['openalex_id'],'title':p['title'],
                'abstract':p['abstract'][:2200],'abstract_truncated':len(p['abstract'])>2200},'courses':selected})
assert len(cases)==32
(OUT/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
stop={'with','from','this','that','their','which','using','based','have','will','study','research','course','these','through','different','students','method','methods','introduction','applications','understanding','theory'}
def words(s):return set(re.findall(r'[a-z]{4,}',s.lower()))-stop
def sentences(s):return [x.strip() for x in re.split(r'(?<=[.!?])\s+|\n+',s) if len(x.strip())>=30]
base=[];rule=[]
for case in cases:
 g=catalog.guide(case['lab_id'],[c['id'] for c in case['courses']]);chunks=[]
 for heading,k in [('지금 시작','start_now'),('추가 준비','prepare_next')]:
  for t in g[k]:
   chunks.append(heading+' | '+t['title']+' | '+t['basis']+' | '+' '.join(t['steps'])+' | 학습 후보: '+', '.join(x['name'] for x in t['courses'])+' | 연구실 원문: '+'; '.join(e.get('text','') for e in t['evidence']))
 base.append({'case_id':case['id'],'text':'수강 표시: '+', '.join(c['name'] for c in g['selected_courses'])+'\n'+'\n'.join(chunks)})
 research=sentences(case['paper']['abstract']); course_text=sentences(' '.join(c['description']+'\n'+c['plan'] for c in case['courses']))
 candidates=sorted(((len(words(a)&words(b)),a,b) for a in research for b in course_text),reverse=True)
 pair=candidates[0] if candidates and candidates[0][0]>=2 else None
 course_note=('과목과 논문에 공통으로 나타나는 표현을 확인할 후보: '+pair[2][:220]+' (과목 '+case['courses'][0]['id']+'). 실제 활용 관계는 미확인.' if pair else '선택 과목 내용과 연구 사이의 구체적 연결은 확인되지 않았습니다.')
 text=('탐색 질문: '+case['interest']+' 이 관심을 선택 논문에서 어떻게 다루는지 살펴보세요.\n'
       '논문 근거 ['+case['paper']['id']+']: '+(pair[1] if pair else (research[0] if research else case['paper']['title']))[:260]+'\n'
       '수업 연결: '+course_note+'\n'
       '첫 단계: 논문 초록에서 연구 문제와 방법을 표시하고 이해가 필요한 용어를 정리해 보세요.\n'
       '확인할 점: 현재 연구실 프로젝트나 자료·장비 접근 가능 여부는 확인되지 않았습니다.')
 rule.append({'case_id':case['id'],'text':text})
(OUT/'baseline.json').write_text(json.dumps(base,ensure_ascii=False,indent=2))
(OUT/'rule.json').write_text(json.dumps(rule,ensure_ascii=False,indent=2))
print('labs',len(scenarios),'cases',len(cases),'no courses',sum(not c['courses'] for c in cases))
