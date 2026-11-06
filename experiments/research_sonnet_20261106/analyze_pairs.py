import collections,json
from pathlib import Path
root=Path(__file__).resolve().parent
key=json.loads((root/'pair_key.json').read_text()); votes=[x for i in range(1,4) for x in json.loads((root/f'pairvotes{i}.json').read_text())]
assert len(votes)==24 and {v['id'] for v in votes}==set(key)
rows=[]
for v in votes:
 assert v['winner'] in ('left','right','tie') and v['reason']
 ref=key[v['id']]; winner=v['winner'] if v['winner']=='tie' else ref[v['winner']]
 rows.append({'case_id':ref['case_id'],'winner':winner,'reason':v['reason']})
counts=collections.Counter(r['winner'] for r in rows)
result={'n':len(rows),'g_wins':counts['g'],'s_wins':counts['s'],'ties':counts['tie'],'rows':rows}
(root/'pair_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
