import collections,json,random,statistics
from pathlib import Path

root=Path(__file__).resolve().parent
cases={c['id']:c for c in json.loads((root/'cases.json').read_text())};key=json.loads((root/'key.json').read_text())
metrics=('interest','lab','course','action','caution');result={};panels={}
corrections=[]
for panel in (1,2):
 rows=[r for p in 'abc' for r in json.loads((root/f'luna{panel}{p}.json').read_text())]
 assert len(rows)==72 and {r['id'] for r in rows}==set(key)
 for r in rows:
  c=cases[key[r['id']]['case_id']]
  assert all(type(r[x]) is int and 0<=r[x]<=2 for x in metrics if x!='course')
  if not c['courses'] and r['course'] is not None:
   corrections.append({'panel':panel,'id':r['id'],'raw':r['course'],'reason':'no course selected; not applicable'})
   r['course']=None
  assert (r['course'] is None) if not c['courses'] else (type(r['course']) is int and 0<=r['course']<=2)
  assert r['reason']
 panels[panel]={r['id']:r for r in rows}
 out={}
 for m in ('a','s','g'):
  out[m]={}
  for met in metrics:
   clusters=collections.defaultdict(list)
   for r in rows:
    item=key[r['id']]; c=cases[item['case_id']]
    if item['method']==m and r[met] is not None:clusters[c['cluster']].append(r[met])
   out[m][met]={'mean':statistics.mean(statistics.mean(v) for v in clusters.values()),
                'n':sum(map(len,clusters.values())),'full_n':sum(x==2 for v in clusters.values() for x in v),
                'zero_n':sum(x==0 for v in clusters.values() for x in v)}
 result[str(panel)]={'methods':out}
 by={(key[r['id']]['method'],key[r['id']]['case_id']):r for r in rows}
 for met in ('course','action'):
  clusters=collections.defaultdict(list)
  for cid,c in cases.items():
   a=by['g',cid][met];b=by['s',cid][met]
   if a is not None and b is not None:clusters[c['cluster']].append(a-b)
  vals=[statistics.mean(v) for v in clusters.values()];rng=random.Random(20261106)
  boots=sorted(statistics.mean(rng.choice(vals) for _ in vals) for _ in range(4000))
  result[str(panel)]['g_minus_s_'+met]={'diff':statistics.mean(vals),'bootstrap95':[boots[99],boots[3899]],'clusters':len(vals)}
 baseline=[r for r in rows if key[r['id']]['method']=='a' and r['course'] is not None]
 result[str(panel)]['baseline_calibration']={'n':len(baseline),'course_zero':sum(r['course']==0 for r in baseline),
                                             'action_le1':sum(r['action']<=1 for r in baseline)}
agreement={}
for met in metrics:
 pairs=[(panels[1][i][met],panels[2][i][met]) for i in key if panels[1][i][met] is not None]
 observed=statistics.mean((a-b)**2/4 for a,b in pairs);expected=statistics.mean((a-b)**2/4 for a,_ in pairs for _,b in pairs)
 agreement[met]={'n':len(pairs),'exact':sum(a==b for a,b in pairs), 'weighted_kappa':1-observed/expected if expected else None}
result['agreement']=agreement
result['not_applicable_corrections']=corrections
(root/'luna_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
