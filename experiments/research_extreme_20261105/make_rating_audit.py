import json,random
from pathlib import Path
root=Path(__file__).resolve().parent
key=json.loads((root/'key.json').read_text()); packets=[json.loads((root/f'packet{i}.json').read_text()) for i in range(1,4)]
answers={a['id']:(a,p['contexts'][a['context_id']]) for p in packets for a in p['answers']}
ratings={v:{r['id']:r for part in 'abc' for r in json.loads((root/f'ratings{v}{part}.json').read_text())} for v in (1,2)}
rng=random.Random(20261106); selected=[]
for method in ('baseline','rule','single','grounded','verified'):
 selected.extend(rng.sample(sorted(k for k,x in key.items() if x['method']==method),4))
target='P3R034'
if target not in selected:selected.append(target)
items=[]
for idx,id_ in enumerate(selected,1):
 answer,context=answers[id_];items.append({'audit_id':f'A{idx:02}', 'source_id':id_, 'context':context,'answer':answer['answer'],
                                      'rating1':ratings[1][id_], 'rating2':ratings[2][id_]})
(root/'rating_audit_packet.json').write_text(json.dumps(items,ensure_ascii=False,indent=2))
print('random per method 20 plus targeted',len(items))
