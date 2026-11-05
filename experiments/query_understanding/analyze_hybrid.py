import sys,json,collections as C
sys.path.insert(0,'.'); sys.path.insert(0,'experiments/query_understanding')
import evaluate as ev
from curri.profile_catalog import ProfileCatalog
from rule_interpreter import interpret
R=json.load(open('experiments/query_understanding/V1/ranks_v1.json')); I=json.load(open('/home/ubuntu/.gpu-hub/outputs/20261011-102059-query-understanding-v1/interp_v1.json'))
cat=ProfileCatalog('data'); Q=ev.Q
R['A']=ev.rules_ranks()
def mean(name,qs,key):
    v=[ev.metrics(R[name][q['id']],q).get(key) for q in qs]; v=[x for x in v if x is not None]; return round(sum(v)/len(v),2) if v else None
ok=[q for q in Q if q['id'] not in ('q18','q32')]
print('LLM 형식 실패 2건 제외(37건) p5:', {m:mean(m,ok,'p5') for m in ['A','B1','C1_l1','D1_l1']})
# A + 해석: 좋아함 구절만 사전 검색, 싫어함 개념의 연구실은 뒤로
def a_interp(q, it):
    likes=' '.join(it['likes']) or q['text']
    base=[r['id'] for r in cat.search(likes)]
    bad=set()
    for d in it['dislikes']:
        bad|=cat.concepts_in(d)
    prof={lid:{t['concept'] for t in cat.profiles[lid]['topics'] if t.get('weight','primary')=='primary'} for lid in cat.profiles}
    front=[l for l in base if not (prof[l]&bad)]; back=[l for l in base if prof[l]&bad]
    return front+back
R['A+rule']={q['id']:a_interp(q,I['rule'][q['id']]) for q in Q}
R['A+llm']={q['id']:a_interp(q,I['llm'][q['id']]) for q in Q}
def rrf(*lists,k=10):
    s=C.defaultdict(float)
    for L in lists:
        for i,l in enumerate(L): s[l]+=1/(k+i+1)
    return [l for l,_ in sorted(s.items(),key=lambda x:-x[1])]
R['RRF(A+rule,C1)']={q['id']:rrf(R['A+rule'][q['id']],R['C1_l1'][q['id']]) for q in Q}
R['RRF(A+llm,D1)']={q['id']:rrf(R['A+llm'][q['id']],R['D1_l1'][q['id']]) for q in Q}
types=['simple','paraphrase','compound','multi','negation','soft_negation']
print('method'.ljust(18),*[t[:9].ljust(10) for t in types],'all'.ljust(6),'viol_any(neg+soft)')
for m in ['A','A+rule','A+llm','C1_l1','D1_l1','RRF(A+rule,C1)','RRF(A+llm,D1)']:
    row=[mean(m,[q for q in Q if q['type']==t],'p5') for t in types]
    neg=[q for q in Q if q['neg']]
    print(m.ljust(18),*[str(x).ljust(10) for x in row],str(mean(m,Q,'p5')).ljust(6),mean(m,neg,'viol_any'),mean(m,neg,'viol5'))
# per-query win/loss A vs C1_l1
w=C.Counter()
for q in Q:
    a=ev.metrics(R['A'][q['id']],q)['p5']; c=ev.metrics(R['C1_l1'][q['id']],q)['p5']
    w['C이김' if c>a else 'A이김' if a>c else '비김']+=1
print('p5 질의별 A vs C1_l1:',dict(w))
# 질의별 q15
for m in ['A','B0','C1_l1','D1_l1']:
    top=R[m]['q15'][:5]; print('q15',m,[ (l[-4:],sorted(ev.prim[l])[:2]) for l in top])
# cases C worse than A
for q in Q:
    a=ev.metrics(R['A'][q['id']],q)['p5']; c=ev.metrics(R['C1_l1'][q['id']],q)['p5']
    if a-c>=0.4: print('A>>C',q['id'],q['type'],q['text'],a,c)
    if c-a>=0.4: print('C>>A',q['id'],q['type'],q['text'],a,c)
json.dump({m:R[m] for m in R if m.startswith(('A+','RRF'))},open('experiments/query_understanding/V1/ranks_hybrid_post.json','w'),ensure_ascii=False)
