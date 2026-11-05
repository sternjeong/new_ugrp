import json
import math
import random
import statistics
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
old = root / 'experiments/final_graph/results/embedding_field_ablation_v1'
packet = json.loads((old/'packet.json').read_text())
frame = json.loads((old/'frame.json').read_text())
score = {r['pair_id']:r for r in json.loads((out/'scores.json').read_text())['rows']}
component = {lid: c['component_id'] for c in frame['buckets']['confirm_unused'] for lid in c['lab_ids']}

def ndcg(order, labels):
    dcg = lambda ids: sum((2**labels[i]-1)/math.log2(rank+2) for rank,i in enumerate(ids[:5]))
    ideal = sorted(labels, key=lambda i:(-labels[i], i))
    return dcg(order)/dcg(ideal)

result = {}
for judge in ('a','b'):
    ratings = {r['pair_id']:r for r in json.loads((old/f'judge_{judge}.json').read_text())['ratings']}
    labs = {}
    for pair in packet['pairs']:
        pid=pair['pair_id']; rating=ratings.get(pid)
        if rating and not rating['insufficient_evidence'] and pid in score:
            labs.setdefault(pair['lab_id'],[]).append((pair, rating['relevance']))
    by_component={}; per_lab=[]
    for lid, pairs in labs.items():
        labels={p['pair_id']: rel for p,rel in pairs}
        if len(labels)<5 or not any(labels.values()): continue
        vals={}
        for method in ('baseline','snippet'):
            order=sorted(labels, key=lambda pid:(-score[pid][method],pid))
            vals[method]={'ndcg5':ndcg(order,labels), 'precision5':sum(labels[i]==2 for i in order[:5])/5,
                          'zero5':sum(labels[i]==0 for i in order[:5])/5}
        item={'lab_id':lid,'component_id':component[lid],'candidates':len(labels), **vals}
        per_lab.append(item);by_component.setdefault(component[lid],[]).append(item)
    comps=list(by_component.values()); rng=random.Random(20261105)
    summary={}
    for metric in ('ndcg5','precision5','zero5'):
        comp_values=[{m:statistics.mean(x[m][metric] for x in group) for m in ('baseline','snippet')} for group in comps]
        a=statistics.mean(x['baseline'] for x in comp_values); b=statistics.mean(x['snippet'] for x in comp_values)
        boot=sorted(statistics.mean((v:=rng.choice(comp_values))['snippet']-v['baseline'] for _ in comp_values) for _ in range(2000))
        summary[metric]={'baseline':a,'snippet':b,'difference':b-a,'bootstrap95':[boot[49],boot[1949]]}
    result[judge]={'labs':len(per_lab),'components':len(comps),'pairs_with_sufficient_evidence':sum(len(x) for x in labs.values()),'metrics':summary,'per_lab':per_lab}
(out/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({j:{k:v for k,v in d.items() if k!='per_lab'} for j,d in result.items()},indent=2))
