import json,random
from pathlib import Path
p=Path(__file__).resolve().parent;src=json.loads((p/'cases_controls.json').read_text());rows=[];key={}
changes=[('550 °C','650 °C'),('충분조건','필요조건'),('102개 행동 범주','120개 행동 범주'),
         ('초록만으로는 특정 성장 기구를 설명했는지 확인할 수 없습니다','초록은 특정 성장 기구를 상세하게 설명합니다'),
         ('1.64배','1.46배'),('비교 가능했다고','항상 더 뛰어났다고')]
for i,(old,new) in enumerate(changes,1):
 x=next(r for r in src if r['id']==f'control_{i:02}_normal');assert old in x['answer']
 for altered in (False,True):
  rows.append({'context':x['context'],'answer':x['answer'].replace(old,new,1) if altered else x['answer'],
               '_altered':altered,'_case':i})
random.Random(20261108).shuffle(rows);clean=[]
for i,x in enumerate(rows,1):
 id_=f'M{i:02}';key[id_]={'altered':x.pop('_altered'),'case':x.pop('_case')};clean.append({'id':id_,**x})
(p/'minimal_blind.json').write_text(json.dumps(clean,ensure_ascii=False,indent=2))
(p/'minimal_key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
print('12 blinded items')
