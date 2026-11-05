import json,re,statistics
from pathlib import Path

root=Path(__file__).resolve().parent
cases={c['id']:c for c in json.loads((root/'cases.json').read_text())}
key=json.loads((root/'key.json').read_text())
packet={r['id']:r for r in json.loads((root/'blind_packet.json').read_text())}
import sys
source=sys.argv[1] if len(sys.argv)>1 else 'judgments.json'
judgments=json.loads((root/source).read_text())
assert len(judgments)==18 and {j['id'] for j in judgments}==set(key)
metrics=('interest','lab','course','action','caution')
for j in judgments:
 assert all(type(j.get(m)) is int and 0<=j[m]<=2 for m in metrics)
 assert isinstance(j.get('reason'),str) and j['reason']
results={}
for method in ('baseline','single','grounded'):
 js=[j for j in judgments if key[j['id']]['method']==method]
 results[method]={'n':len(js),'means':{m:statistics.mean(j[m] for j in js) for m in metrics},
                  'all_dimensions_at_least_1':sum(all(j[m]>=1 for m in metrics) for j in js),
                  'case_rows':[{**key[j['id']],'scores':{m:j[m] for m in metrics},'reason':j['reason']} for j in js]}
for method in ('single','grounded'):
 invalid=[]; has_paper=0; has_course=0
 for item_id,meta in key.items():
  if meta['method']!=method:continue
  case=cases[meta['case_id']]; text=packet[item_id]['answer']
  ids=set(re.findall(r'(?<![A-Za-z0-9])(?:W\d+|(?:CSED|EECE|CHEM|CHEB|DISU)\d+[A-Z]?)(?![A-Za-z0-9])',text))
  allowed={case['paper']['id']}|{c['id'] for c in case['courses']}
  invalid.extend([{'case_id':meta['case_id'],'id':id_} for id_ in sorted(ids-allowed)])
  has_paper+=case['paper']['id'] in ids
  has_course+=any(c['id'] in ids for c in case['courses'])
 results[method]['reference_audit']={'unprovided_ids':invalid,'paper_id_mentions':has_paper,'course_id_mentions':has_course}
(root/('analysis2.json' if source=='judgments2.json' else 'analysis.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({m:{k:v for k,v in data.items() if k!='case_rows'} for m,data in results.items()},ensure_ascii=False,indent=2))
