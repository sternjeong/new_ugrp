import json,random
from pathlib import Path
from curri.curated_catalog import CuratedCatalog

out=Path(__file__).resolve().parent
root=out.parents[1]
cases={c['id']:c for c in json.loads((out/'cases.json').read_text())}
catalog=CuratedCatalog(root/'data/sunwoo')
items=[]
for method in ('baseline','single','grounded'):
 rows=json.loads((out/(method+'.json')).read_text())
 assert len(rows)==len(cases) and {r['case_id'] for r in rows}==set(cases)
 for row in rows:
  case=cases[row['case_id']]
  # The current baseline may use other research-lab source material, so make those
  # sources available to the evaluator without telling it which method produced text.
  topics=catalog.profiles[case['lab_id']]['topics'][:3]
  sources=[{'label':t['label_ko'],'text':t['quote']} for t in topics]
  items.append({'case':case,'lab_sources':sources,'answer':row['text'],'method':method})
random.Random(20261105).shuffle(items)
mapping={}; packet=[]
for i,item in enumerate(items,1):
 item_id=f'R{i:02d}';mapping[item_id]={'case_id':item['case']['id'],'method':item.pop('method')}
 packet.append({'id':item_id,**item})
(out/'blind_packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
(out/'key.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
print('blinded responses',len(packet))
