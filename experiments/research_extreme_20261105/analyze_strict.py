import json,random,statistics,collections
from pathlib import Path
root=Path(__file__).resolve().parent
key=json.loads((root/'key.json').read_text()); cases={x['id']:x for x in json.loads((root/'cases.json').read_text())}
rows=[r for i in range(1,4) for r in json.loads((root/f'strict{i}.json').read_text())]
assert len(rows)==160 and {r['id'] for r in rows}==set(key)
corrected=[]
for r in rows:
 c=cases[key[r['id']]['case_id']]
 assert type(r['action']) is int and 0<=r['action']<=2
 if not c['courses'] and r['course'] is not None:
  corrected.append({'id':r['id'],'raw':r['course'],'reason':'no selected course; metric not applicable'})
  r['course']=None
 assert (r['course'] is None) if not c['courses'] else (type(r['course']) is int and 0<=r['course']<=2)
by={m:{} for m in ('baseline','rule','single','grounded','verified')}
for r in rows:
 k=key[r['id']];by[k['method']][k['case_id']]=r
out={}
for method,records in by.items():
 out[method]={}
 for field in ('course','action'):
  clusters=collections.defaultdict(list)
  for cid,r in records.items():
   if r[field] is not None:clusters[cases[cid]['cluster']].append(r[field])
  out[method][field]={'mean':statistics.mean(statistics.mean(v) for v in clusters.values()),
                      'n':sum(map(len,clusters.values())), 'full_n':sum(x==2 for v in clusters.values() for x in v),
                      'zero_n':sum(x==0 for v in clusters.values() for x in v)}
comp={}
for left,right in [('grounded','single'),('verified','grounded')]:
 for field in ('course','action'):
  d=collections.defaultdict(list)
  for cid,r in by[left].items():
   a=r[field];b=by[right][cid][field]
   if a is not None and b is not None:d[cases[cid]['cluster']].append(a-b)
  vals=[statistics.mean(v) for v in d.values()];rng=random.Random(20261105)
  boots=sorted(statistics.mean(rng.choice(vals) for _ in vals) for _ in range(4000))
  comp[left+'-'+right+'_'+field]={'diff':statistics.mean(vals),'interval95':[boots[99],boots[3899]]}
result={'methods':out,'comparisons':comp,'not_applicable_corrections':corrected}
(root/'strict_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
