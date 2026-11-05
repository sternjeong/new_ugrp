"""Post-hoc randomized direct comparison: S/G and G/V, same inputs."""
import json,random
from pathlib import Path
root=Path(__file__).resolve().parent
cases=json.loads((root/'cases.json').read_text());cl=list(dict.fromkeys(c['cluster'] for c in cases))
variants={m:{r['case_id']:r['text'] for r in json.loads((root/(m+'.json')).read_text())} for m in ('single','grounded','verified')}
rng=random.Random(20261106);mapping={}
for part in range(3):
 contexts={};items=[]
 selected=[c for c in cases if cl.index(c['cluster'])%3==part]
 for i,c in enumerate(selected):
  cid=f'PC{part+1}-{i+1:02}';contexts[cid]={k:v for k,v in c.items() if k not in ('id','condition','cluster')}
  for x,y in [('single','grounded'),('grounded','verified')]:
   left,right=(x,y) if rng.randrange(2) else (y,x)
   items.append({'context_id':cid,'left':variants[left][c['id']],'right':variants[right][c['id']],
                 '_case':c['id'],'_left':left,'_right':right})
 rng.shuffle(items);clean=[]
 for i,r in enumerate(items,1):
  id_=f'Q{part+1}-{i:03}';mapping[id_]={'case_id':r['_case'],'left':r['_left'],'right':r['_right']}
  clean.append({k:v for k,v in {'id':id_,'context_id':r['context_id'],'left':r['left'],'right':r['right']}.items()})
 (root/f'pairwise{part+1}.json').write_text(json.dumps({'contexts':contexts,'pairs':clean},ensure_ascii=False,indent=2))
 print(part+1,len(clean))
(root/'pairwise_key.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
