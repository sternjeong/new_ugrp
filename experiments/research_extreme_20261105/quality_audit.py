"""Post-hoc checks of judge consistency against visible baseline and duplicated steps."""
import collections,json
from pathlib import Path
root=Path(__file__).resolve().parent
key=json.loads((root/'key.json').read_text()); result={}
for panel in (1,2):
 rows=[r for p in 'abc' for r in json.loads((root/f'ratings{panel}{p}.json').read_text())]
 baseline=[r for r in rows if key[r['id']]['method']=='baseline' and r['course'] is not None]
 result[f'panel{panel}_baseline_course']={'n':len(baseline),'zero':sum(r['course']==0 for r in baseline),
   'one':sum(r['course']==1 for r in baseline),'two':sum(r['course']==2 for r in baseline)}
for method in ('single','grounded','verified'):
 rows=json.loads((root/(method+'.json')).read_text())
 steps=[r['text'].split('첫 단계:',1)[1].split('확인할 점:',1)[0].strip() for r in rows]
 counts=collections.Counter(steps)
 result[method+'_steps']={'n':len(steps),'unique':len(counts),'most_repeated':counts.most_common(1)[0][1]}
(root/'quality_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
