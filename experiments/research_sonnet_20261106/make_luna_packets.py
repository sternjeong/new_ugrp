"""Fallback: no partial verifier comparison. Blind complete A/S/G outputs for Luna review."""
import json,random
from pathlib import Path
root=Path(__file__).resolve().parent
cases=json.loads((root/'cases.json').read_text());baseline={r['case_id']:r['text'] for r in json.loads((root/'baseline.json').read_text())}
key={}
for part in range(3):
 contexts={}; answers=[]
 for n,c in enumerate(cases[part::3],1):
  cid=f'C{part+1}-{n:02}';contexts[cid]={k:v for k,v in c.items() if k not in ('id','condition','cluster')}
  for method in ('a','s','g'):
   if method=='a':text=baseline[c['id']]
   else:
    record=json.loads((root/'calls/generate'/(method+'_'+c['id']+'.json')).read_text())
    assert record['ok'] and record['value']
    text=json.dumps(record['value'],ensure_ascii=False,indent=2)
   answers.append({'context_id':cid,'answer':text,'_case':c['id'],'_method':method})
 random.Random(20261106+part).shuffle(answers); clean=[]
 for i,a in enumerate(answers,1):
  id_=f'R{part+1}-{i:03}';key[id_]={'case_id':a['_case'],'method':a['_method']}
  clean.append({'id':id_,'context_id':a['context_id'],'answer':a['answer']})
 assert len(clean)==24
 (root/f'packet{part+1}.json').write_text(json.dumps({'contexts':contexts,'answers':clean},ensure_ascii=False,indent=2))
(root/'key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
print('3 packets; 72 blinded responses')
