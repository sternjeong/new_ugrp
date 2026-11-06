import copy,json,random
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
source=root/'experiments/research_sonnet_20261106'; cases=json.loads((source/'cases.json').read_text())
chosen=[c for c in cases if c['condition']=='course1'][:4];items=[]
for c in chosen:
 original=json.loads((source/'calls/generate'/('s_'+c['id']+'.json')).read_text())['value']
 altered=copy.deepcopy(original)
 altered['course_connection']+=' 또한 이 수업의 공식 강의계획은 이 논문을 수업 중 직접 재현하는 실습을 명시합니다.'
 for flag,answer in [(False,original),(True,altered)]:
  items.append({'context':c,'answer':answer,'_altered':flag})
random.Random(20261106).shuffle(items);key={};rows=[]
for i,x in enumerate(items,1):
 id_=f'T{i:02}';key[id_]=x.pop('_altered');rows.append({'id':id_,**x})
(out/'control_packet.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
(out/'control_key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
print('4 original + 4 inserted unsupported claims')
