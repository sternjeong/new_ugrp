"""Post-hoc direct S/G comparison; one single judge per pair, no V subset."""
import json,random
from pathlib import Path
root=Path(__file__).resolve().parent;cases=json.loads((root/'cases.json').read_text());rng=random.Random(20261106);key={}
for p in range(3):
 contexts={};pairs=[]
 for i,c in enumerate(cases[p::3],1):
  ctx=f'C{p+1}-{i:02}';contexts[ctx]={k:v for k,v in c.items() if k not in ('id','condition','cluster')}
  left,right=('s','g') if rng.randrange(2) else ('g','s')
  get=lambda m:json.loads((root/'calls/generate'/(m+'_'+c['id']+'.json')).read_text())['value']
  pairs.append({'context_id':ctx,'left':get(left),'right':get(right),'_case':c['id'],'_left':left,'_right':right})
 rng.shuffle(pairs);clean=[]
 for i,x in enumerate(pairs,1):
  id_=f'P{p+1}-{i:02}';key[id_]={'case_id':x['_case'],'left':x['_left'],'right':x['_right']}
  clean.append({'id':id_,'context_id':x['context_id'],'left':x['left'],'right':x['right']})
 (root/f'pair{p+1}.json').write_text(json.dumps({'contexts':contexts,'pairs':clean},ensure_ascii=False,indent=2))
(root/'pair_key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
print('24 balanced blind pairs')
