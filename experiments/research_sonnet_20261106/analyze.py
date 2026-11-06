"""Aggregate separate Sonnet calls; failures remain explicit, paired comparisons need coverage."""
import collections,json,random,re,statistics
from pathlib import Path
root=Path(__file__).resolve().parent
cases=json.loads((root/'cases.json').read_text());methods=('a','s','g','v');metrics=('interest','lab','course','action','caution')
def get(stage,name):
 p=root/'calls'/stage/(name+'.json')
 return json.loads(p.read_text()) if p.exists() else {'ok':False,'error':'missing'}
def model(m,c):return get('generate' if m in ('s','g') else 'verify',m+'_'+c['id'])
def norm(x):return re.sub(r'\s+',' ',x or '').strip()
out={'coverage':{},'citation_audit':{},'scores':{},'differences':{},'agreement':{},'calibration':{},'calls':{}}
for stage in ('pilot','generate','verify','judge'):
 fs=list((root/'calls'/stage).glob('*.json')); values=[json.loads(p.read_text()) for p in fs]
 models=sorted({m for v in values for m in v.get('model_usage',{})})
 out['calls'][stage]={'files':len(fs),'success':sum(bool(v.get('ok')) for v in values),
  'models':models,'sum_list_cost_usd':sum(v.get('cost_usd_list') or 0 for v in values)}
for method in methods:
 gens=[model(method,c) for c in cases] if method!='a' else [{'ok':True} for c in cases]
 out['coverage'][method]={'expected':len(cases),'generation_ok':sum(bool(x.get('ok')) for x in gens)}
 if method!='a':
  rows=[]
  for c,g in zip(cases,gens):
   v=g.get('value') or {};co=c['courses']
   pq=norm(v.get('paper_quote'));cq=norm(v.get('course_quote'))
   rows.append({'case_id':c['id'],'generation_ok':g.get('ok',False),
    'paper_id_ok':v.get('paper_id')==c['paper']['id'],
    'paper_quote_ok':len(pq)>=12 and pq in norm(c['paper']['abstract']),
    'course_id_ok':v.get('course_id')==co[0]['id'] if co else v.get('course_id')=='',
    'course_quote_ok':(len(cq)>=12 and cq in norm(co[0]['description']+' '+co[0]['plan'])) if co else v.get('course_quote')=='',
    'selected':bool(co)})
  out['citation_audit'][method]={'n':len(rows),'paper_id':sum(r['paper_id_ok'] for r in rows),'paper_quote':sum(r['paper_quote_ok'] for r in rows),
   'course_n':sum(r['selected'] for r in rows),'course_id':sum(r['course_id_ok'] for r in rows if r['selected']),
   'course_quote':sum(r['course_quote_ok'] for r in rows if r['selected']),
   'none_n':sum(not r['selected'] for r in rows),'none_no_course_id':sum(r['course_id_ok'] for r in rows if not r['selected']),
   'rows':rows}
 for judge in (1,2):
  scored={c['id']:get('judge',f'{judge}_{method}_{c["id"]}') for c in cases}
  stat={'success':sum(bool(v.get('ok')) for v in scored.values()),'metrics':{}}
  for met in metrics:
   clusters=collections.defaultdict(list);missing=[]
   for c in cases:
    if met=='course' and not c['courses']:continue
    raw=scored[c['id']]; val=(raw.get('value') or {}).get(met)
    if raw.get('ok') and type(val) is int and 0<=val<=2:clusters[c['cluster']].append(val)
    else:missing.append(c['id'])
   stat['metrics'][met]={'mean':statistics.mean(statistics.mean(x) for x in clusters.values()) if clusters else None,
                         'n':sum(map(len,clusters.values())),'clusters':len(clusters),'missing':missing,
                         'full_n':sum(x==2 for v in clusters.values() for x in v),
                         'zero_n':sum(x==0 for v in clusters.values() for x in v)}
  out['scores'][f'{judge}_{method}']=stat
for judge in (1,2):
 for x,y in [('g','s'),('v','g')]:
  for met in ('course','action'):
   clusters=collections.defaultdict(list);missing=[]
   for c in cases:
    if met=='course' and not c['courses']:continue
    aa=get('judge',f'{judge}_{x}_{c["id"]}');bb=get('judge',f'{judge}_{y}_{c["id"]}')
    a=(aa.get('value') or {}).get(met);b=(bb.get('value') or {}).get(met)
    if aa.get('ok') and bb.get('ok') and type(a) is int and type(b) is int:clusters[c['cluster']].append(a-b)
    else:missing.append(c['id'])
   if clusters:
    diffs=[statistics.mean(x) for x in clusters.values()];rng=random.Random(20261106)
    boot=sorted(statistics.mean(rng.choice(diffs) for _ in diffs) for _ in range(4000))
    out['differences'][f'{judge}_{x}-{y}_{met}']={'difference':statistics.mean(diffs),'interval95':[boot[99],boot[3899]],'missing':missing,'clusters':len(diffs)}
for met in metrics:
 pairs=[]
 for m in methods:
  for c in cases:
   if met=='course' and not c['courses']:continue
   a=get('judge',f'1_{m}_{c["id"]}');b=get('judge',f'2_{m}_{c["id"]}')
   aa=(a.get('value') or {}).get(met);bb=(b.get('value') or {}).get(met)
   if a.get('ok') and b.get('ok') and type(aa) is int and type(bb) is int:pairs.append((aa,bb))
 if pairs:out['agreement'][met]={'n':len(pairs),'exact':sum(a==b for a,b in pairs),'mean_absolute_difference':statistics.mean(abs(a-b) for a,b in pairs)}
for judge in (1,2):
 vv=[(get('judge',f'{judge}_a_{c["id"]}').get('value') or {}) for c in cases if c['courses']]
 out['calibration'][str(judge)]={'expected':len(vv),'n':sum(bool(x) for x in vv),'baseline_course_zero':sum(x.get('course')==0 for x in vv),
                                  'baseline_action_le1':sum(type(x.get('action')) is int and x['action']<=1 for x in vv)}
(root/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ('citation_audit','scores')},ensure_ascii=False,indent=2))
