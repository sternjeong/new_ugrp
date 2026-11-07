import json,statistics
from pathlib import Path
p=Path(__file__).resolve().parent
key={r['id']:r for r in json.loads((p/'answers_key.json').read_text())}
mapping=json.loads((p/'blinding_key.json').read_text());rows=json.loads((p/'blinded.json').read_text())
assert len(rows)==len(key)==12 and len(mapping)==12
out={}
for i in (1,2):
 ratings=json.loads((p/f'blind_ratings{i}.json').read_text());assert {r['id'] for r in ratings}==set(mapping)
 assert all(type(r['flagged']) is bool for r in ratings)
 out[f'judge{i}']={'injected_total':sum(key[mapping[r['id']]]['altered'] for r in ratings),
  'injected_flagged':sum(key[mapping[r['id']]]['altered'] and r['flagged'] for r in ratings),
  'original_total':sum(not key[mapping[r['id']]]['altered'] for r in ratings),
  'original_flagged':sum(not key[mapping[r['id']]]['altered'] and r['flagged'] for r in ratings)}
lengths={label:[len(r['answer']) for r in rows if key[mapping[r['id']]]['altered']==label] for label in (False,True)}
out['answer_lengths']={str(k):{'min':min(v),'max':max(v),'mean':statistics.mean(v)} for k,v in lengths.items()}
minimal=json.loads((p/'minimal_key.json').read_text())
for i in (1,2):
 ratings=json.loads((p/f'minimal_ratings{i}.json').read_text());assert {r['id'] for r in ratings}==set(minimal)
 out[f'minimal_judge{i}']={'injected_flagged':sum(minimal[r['id']]['altered'] and r['flagged'] for r in ratings),
  'injected_total':sum(minimal[r['id']]['altered'] for r in ratings),
  'original_flagged':sum(not minimal[r['id']]['altered'] and r['flagged'] for r in ratings),
  'original_total':sum(not minimal[r['id']]['altered'] for r in ratings)}
for i in (1,2):
 k=json.loads((p/f'isolated_key{i}.json').read_text());ratings=json.loads((p/f'isolated_ratings{i}.json').read_text())
 assert len(ratings)==6 and {r['id'] for r in ratings}==set(k)
 out[f'isolated_judge{i}']={'injected_flagged':sum(k[r['id']]['altered'] and r['flagged'] for r in ratings),
  'injected_total':sum(k[r['id']]['altered'] for r in ratings),
  'original_flagged':sum(not k[r['id']]['altered'] and r['flagged'] for r in ratings),
  'original_total':sum(not k[r['id']]['altered'] for r in ratings),
  'empty_reasons':sum(not r.get('reason') for r in ratings)}
(p/'metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,indent=2))
