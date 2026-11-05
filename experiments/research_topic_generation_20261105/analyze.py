import json,re
from pathlib import Path

root=Path(__file__).resolve().parent
cases={c['id']:c for c in json.loads((root/'cases.json').read_text())}
result=json.loads((root/'generations.json').read_text())
rows=[]
for row in result['outputs']:
 c=cases[row['case_id']]; text=row['text']; ids=set(re.findall(r'\b(?:W\d+|(?:CSED|EECE|CHEM|CHEB)\d+[A-Z]?)\b',text))
 allowed={c['paper']['id']}|{x['id'] for x in c['courses']}
 rows.append({'case_id':c['id'],'method':row['method'],'nonempty':bool(text.strip()),
              'paper_id':c['paper']['id'] in ids,'course_id':any(x['id'] in ids for x in c['courses']),
              'invented_ids':sorted(ids-allowed),'mentions_unselected_course_id':bool(not c['courses'] and any(not x.startswith('W') for x in ids)),
              'tokens':row['tokens']})
summary={}
for method in ('A','B'):
 rr=[r for r in rows if r['method']==method]; enrolled=[r for r in rr if cases[r['case_id']]['courses']]; none=[r for r in rr if not cases[r['case_id']]['courses']]
 summary[method]={'outputs':len(rr),'nonempty':sum(r['nonempty'] for r in rr),'paper_id':sum(r['paper_id'] for r in rr),
                  'selected_course_id':sum(r['course_id'] for r in enrolled),'with_course':len(enrolled),
                  'any_unprovided_id':sum(bool(r['invented_ids']) for r in rr),
                  'unselected_course_id_on_none':sum(r['mentions_unselected_course_id'] for r in none),'none':len(none),
                  'at_250_token_cap':sum(r['tokens']>=250 for r in rr)}
lookup={(x['case_id'],x['method']):x['text'] for x in result['outputs']}
for method in ('A','B'):
 for cond in ('interest','course','none'):
  summary[method]['changed_'+cond]=sum(lookup[(g+'_base',method)]!=lookup[(g+'_'+cond,method)] for g in ('sensor','robot','chem'))
(root/'metrics.json').write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
