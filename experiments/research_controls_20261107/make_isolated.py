import json,random
from pathlib import Path
p=Path(__file__).resolve().parent
rows=json.loads((p/'minimal_blind.json').read_text());key=json.loads((p/'minimal_key.json').read_text())
lookup={(key[r['id']]['case'],key[r['id']]['altered']):r for r in rows}
for n in (1,2):
 chosen=[];mapping={}
 for i in range(1,7):
  altered=(i%2==1) if n==1 else (i%2==0)
  chosen.append((lookup[(i,altered)],altered,i))
 random.Random(101+n).shuffle(chosen);out=[]
 for i,(row,altered,case) in enumerate(chosen,1):
  id_=f'Z{n}{i}';out.append({**row,'id':id_});mapping[id_]={'case':case,'altered':altered}
 (p/f'isolated{n}.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 (p/f'isolated_key{n}.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
print('two counterbalanced single-version packets')
