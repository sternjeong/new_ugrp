import json,math,sys
from pathlib import Path
sys.path.insert(0,'.')
from curri.curated_catalog import CuratedCatalog
from curri.curated_query_engine import CuratedQueryEngine
OUT=Path('experiments/engine_strategies_20261109')
doc=json.load(open(Path.home()/'.gpu-hub/outputs/20261109-065901-gpu-strategies/doc_sims.json'))
T={p:{'sims':dict(zip(doc['lab_ids'],doc['sims'][p])),'best':dict(zip(doc['lab_ids'],doc['best'][p]))} for p in doc['sims']}
class R:
    def request(self,ph,t,remote=True): return {p:T[p] for p in ph} if all(p in T for p in ph) else None
cat=CuratedCatalog('data/sunwoo'); eng=CuratedQueryEngine(cat,R())
Q=json.load(open(OUT/'queries.json')); old=json.load(open(OUT/'rankings.json'))['rankings']['A0']
pools=json.load(open(OUT/'pools.json'))
from collections import defaultdict
gr=defaultdict(lambda:defaultdict(list)); votes=defaultdict(list)
for q in Q:
    for j in range(1,6):
        r=json.load(open(OUT/'calls'/f"{q['id']}_j{j}.json"))
        votes[q['id']].append(r['value']['should_recommend'])
        for g in r['value']['grades']: gr[q['id']][r['key'][g['label']]].append(g['grade'])
gain={k:{l:sum(v)/len(v) for l,v in x.items()} for k,x in gr.items()}
dcg=lambda g:sum(x/math.log2(i+2) for i,x in enumerate(g))
new={};modes={}
for q in Q:
    f=eng.search(q['text']); new[q['id']]=[c['id'] for c in f['labs']][:10] if f['intent']=='search' else None; modes[f['mode']]=modes.get(f['mode'],0)+1
print(modes)
tot={'old':[], 'new':[]}; unj=0; n=0; diffs=[]
for q in Q:
    k=q['id']
    if sum(votes[k])<=len(votes[k])/2: continue
    pg={l:g for l,g in gain[k].items() if l not in pools[k]['controls']}
    I=dcg(sorted(pg.values(),reverse=True)[:5]) or 1
    a=dcg([gain[k].get(l,0) for l in (old[k] or [])[:5]])/I
    b=dcg([gain[k].get(l,0) for l in (new[k] or [])[:5]])/I
    unj+=sum(l not in gain[k] for l in (new[k] or [])[:5]); n+=len((new[k] or [])[:5])
    tot['old'].append(a); tot['new'].append(b); diffs.append((round(b-a,3),k,q['text'][:34],[cat.profiles[l]['professors'][0] for l in (new[k] or [])[:5] if l not in gain[k]]))
print({k:round(sum(v)/len(v),3) for k,v in tot.items()}, 'unjudged in new top5:',unj,'/',n)
diffs.sort(); print(*diffs[:8],sep='\n'); print('...'); print(*diffs[-6:],sep='\n')
Path(sys.argv[1]).write_text(json.dumps({k:v for k,v in new.items()},ensure_ascii=False))
for t in ['잠이 인체에 영향을 미치는 것을 연구하고 싶다']:
    print(t); ph=None
    for dic in [True]:
        print('dict', [(c['professors'][0],c['department'][:5]) for c in cat.search(t)[:10]])
