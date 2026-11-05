import json,random,statistics,re,sys
from pathlib import Path

root=Path(__file__).resolve().parent
cases={x['id']:x for x in json.loads((root/'cases.json').read_text())}
key=json.loads((root/'key.json').read_text())
packets=[json.loads((root/f'packet{i}.json').read_text()) for i in range(1,4)]
answers={a['id']:a['answer'] for p in packets for a in p['answers']}
assert set(answers)==set(key) and len(key)==160
excluded=sys.argv[1] if len(sys.argv)>1 else None
methods=('baseline','rule','single','grounded','verified')
metrics=('interest','lab','course','action','caution')
result={};all_ratings={}
for reviewer in (1,2):
 ratings=[]
 for part in 'abc': ratings+=json.loads((root/f'ratings{reviewer}{part}.json').read_text())
 assert len(ratings)==len(answers) and {r['id'] for r in ratings}==set(answers)
 for r in ratings:
  case=cases[key[r['id']]['case_id']]
  assert all(type(r[m]) is int and 0<=r[m]<=2 for m in metrics if m!='course')
  assert (r['course'] is None) if not case['courses'] else (type(r['course']) is int and 0<=r['course']<=2)
  assert isinstance(r.get('reason'),str) and r['reason']
 if excluded:
  ratings=[r for r in ratings if key[r['id']]['case_id']!=excluded]
 bymethod={m:{} for m in methods}
 for r in ratings:
  ref=key[r['id']];c=cases[ref['case_id']];bymethod[ref['method']][ref['case_id']]=r
 all_ratings[reviewer]={r['id']:r for r in ratings}
 summaries={}
 for method in methods:
  summaries[method]={}
  for metric in metrics:
   cluster={}
   for caseid,r in bymethod[method].items():
    value=r[metric]
    if value is not None:cluster.setdefault(cases[caseid]['cluster'],[]).append(value)
   summaries[method][metric]={'mean':statistics.mean(statistics.mean(v) for v in cluster.values()),
                               'clusters':len(cluster),'n':sum(map(len,cluster.values())),
                               'full_score_n':sum(x==2 for values in cluster.values() for x in values),
                               'zero_n':sum(x==0 for values in cluster.values() for x in values)}
 comparisons={}
 for left,right in [('grounded','single'),('verified','grounded')]:
  for metric in ('course','caution'):
   cluster={}
   for caseid,r in bymethod[left].items():
    a=r[metric];b=bymethod[right][caseid][metric]
    if a is not None and b is not None:cluster.setdefault(cases[caseid]['cluster'],[]).append(a-b)
   diffs=[statistics.mean(v) for v in cluster.values()];rng=random.Random(20261105)
   boot=sorted(statistics.mean(rng.choice(diffs) for _ in diffs) for _ in range(4000))
   comparisons[f'{left}_minus_{right}_{metric}']={'difference':statistics.mean(diffs),'interval95':[boot[99],boot[3899]],'clusters':len(diffs)}
 result[str(reviewer)]={'methods':summaries,'preplanned_differences':comparisons}
agreement={}
for metric in metrics:
 pairs=[(all_ratings[1][i][metric],all_ratings[2][i][metric]) for i in all_ratings[1] if all_ratings[1][i][metric] is not None]
 observed=statistics.mean((x-y)**2/4 for x,y in pairs)
 expected=statistics.mean((x-y)**2/4 for x,_ in pairs for _,y in pairs)
 agreement[metric]={'exact_n':sum(x==y for x,y in pairs),'n':len(pairs),
                    'mean_absolute_difference':statistics.mean(abs(x-y) for x,y in pairs),
                    'quadratic_weighted_kappa':1-observed/expected if expected else None}
result['agreement']=agreement
audit={}
for method in ('single','grounded','verified'):
 rows=[]
 for id_,ref in key.items():
  if ref['method']!=method:continue
  if excluded and ref['case_id']==excluded:continue
  case=cases[ref['case_id']]; text=answers[id_]
  ids=set(re.findall(r'(?<![A-Za-z0-9])(?:W\d+|[A-Z]{2,7}\d{3}[A-Z]?)(?![A-Za-z0-9])',text))
  allowed={case['paper']['id']}|{c['id'] for c in case['courses']}
  rows.append({'case_id':ref['case_id'],'paper_id':case['paper']['id'] in ids,
               'course_id':any(c['id'] in ids for c in case['courses']),
               'unprovided_ids':sorted(ids-allowed)})
 audit[method]={'paper_id':sum(x['paper_id'] for x in rows),'course_id':sum(x['course_id'] for x in rows),
                'unprovided_ids':[x for x in rows if x['unprovided_ids']]}
result['id_audit']=audit
(root/('analysis_excluding_case06course2.json' if excluded else 'analysis.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
