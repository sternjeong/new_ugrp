import json,collections
from pathlib import Path
root=Path(__file__).resolve().parent
key=json.loads((root/'pairwise_key.json').read_text());votes=[]
for i in range(1,4):votes+=json.loads((root/f'pairvotes{i}.json').read_text())
assert len(votes)==64 and {v['id'] for v in votes}==set(key)
results={}
for focal,other in [('grounded','single'),('verified','grounded')]:
 rs=[]
 for v in votes:
  k=key[v['id']]
  if {k['left'],k['right']}!={focal,other}:continue
  assert v['winner'] in ('left','right','tie') and v['reason']
  winner='tie' if v['winner']=='tie' else k[v['winner']]
  rs.append({'case_id':k['case_id'],'winner':winner,'reason':v['reason'],'id':v['id']})
 counts=collections.Counter(x['winner'] for x in rs)
 results[focal+'_vs_'+other]={'n':len(rs),focal+'_wins':counts[focal],other+'_wins':counts[other],
                              'ties':counts['tie'],'rows':rs}
 assert len(rs)==32
(root/'pairwise_analysis.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({k:{x:y for x,y in v.items() if x!='rows'} for k,v in results.items()},ensure_ascii=False,indent=2))
