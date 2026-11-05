"""Shuffle method labels and partition by lab; identical packets for two judges."""
import json,random
from pathlib import Path
from curri.curated_catalog import CuratedCatalog

root=Path(__file__).resolve().parents[2]; out=Path(__file__).resolve().parent
cases=json.loads((out/'cases.json').read_text()); byid={x['id']:x for x in cases}
cat=CuratedCatalog(root/'data/sunwoo')
methods=('baseline','rule','single','grounded','verified')
responses={}
for name in methods:
 rows=json.loads((out/(name+'.json')).read_text()); assert len(rows)==len(cases)
 assert {r['case_id'] for r in rows}==set(byid)
 assert all(isinstance(r['text'],str) and r['text'].strip() for r in rows)
 responses[name]={r['case_id']:r['text'] for r in rows}
mapping={}; packets=[]
clusters=list(dict.fromkeys(x['cluster'] for x in cases))
for part in range(3):
 selected=[c for c in cases if clusters.index(c['cluster'])%3==part]
 contexts={}; entries=[]
 for i,c in enumerate(selected):
  casekey=f'P{part+1}C{i+1:02}'
  src={k:v for k,v in c.items() if k not in ('id','condition','cluster')}
  src['lab_sources']=[{'label':t['label_ko'],'text':t['quote']} for t in cat.profiles[c['lab_id']]['topics'][:3]]
  contexts[casekey]=src
  for method in methods:
   entries.append({'context_id':casekey,'answer':responses[method][c['id']],'_case':c['id'],'_method':method})
 random.Random(20261105+part).shuffle(entries)
 clean=[]
 for i,e in enumerate(entries):
  rid=f'P{part+1}R{i+1:03}';mapping[rid]={'case_id':e['_case'],'method':e['_method']}
  clean.append({'id':rid,'context_id':e['context_id'],'answer':e['answer']})
 packet={'contexts':contexts,'answers':clean};packets.append(packet)
 (out/f'packet{part+1}.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2))
 print('packet',part+1,'cases',len(selected),'responses',len(clean))
(out/'key.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2))
