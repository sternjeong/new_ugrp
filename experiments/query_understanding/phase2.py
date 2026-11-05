"""2단계(로컬): 유사도 행렬로 L3~L4를 계산하고 현재 파이프라인(A)과 비교한다. 사용: python3 -I phase2.py <sims_v2.json>  (저장소 루트)
임계값은 개발용 질의(queries.json)에서만 정하고 thresholds_v2.json에 저장한 뒤, 같은 값으로 시험용 질의(queries_test.json)를 평가한다."""
import sys, json, math, statistics as st, collections as C
sys.path.insert(0, '.'); sys.path.insert(0, 'experiments/query_understanding')
from curri.profile_catalog import ProfileCatalog
import pipeline
D = 'experiments/query_understanding/'
S = json.load(open(sys.argv[1], encoding='utf-8'))
lab_ids, SIM = S['lab_ids'], {k: list(v) for k, v in S['sims']['0'].items()}
mean = lambda xs: sum(xs) / len(xs)
def percentile(xs, p):
    xs = sorted(xs); i = (len(xs) - 1) * p / 100; lo = int(i); hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)
class np:   # 필요한 최소 기능만
    mean = staticmethod(lambda xs: mean(list(xs)))
plans = json.load(open(D + 'plans_v2.json', encoding='utf-8'))
dev = json.load(open(D + 'queries.json', encoding='utf-8'))
test = json.load(open(D + 'queries_test.json', encoding='utf-8'))
for q in dev:
    q['intent'] = 'search'
cat = ProfileCatalog('data')
labs = [json.loads(l) for l in open('data/lab_profiles.jsonl', encoding='utf-8')]
prim = {p['lab_id']: {t['concept'] for t in p['topics'] if t.get('weight', 'primary') == 'primary'} for p in labs if p['status'] != 'insufficient'}
K = 5
def zs(x):
    m = mean(x); sd = (sum((v - m) ** 2 for v in x) / len(x)) ** 0.5 + 1e-9
    return [(v - m) / sd for v in x]

# ---- 임계값: 개발용 질의의 '범위 안' 구절·질의에서만 ----
ph = [max(SIM[p]) for q in dev for p in plans[q['id']]['likes']]
qy = [max(SIM[plans[q['id']]['norm']]) for q in dev]
TH = {'phrase': percentile(ph, 10), 'query': percentile(qy, 10)}
json.dump(TH, open(D + 'thresholds_v2.json', 'w'), indent=1)
print('임계값(개발용 10퍼센타일):', {k: round(v, 3) for k, v in TH.items()})

def run_P(q):
    p = plans[q['id']]
    r = {'intent': p['intent'], 'routed': False, 'reasons': [], 'rank': None}
    if p['intent'] != 'search':
        return r
    likes = p['likes'] or [p['norm']]
    zl = [mean(c) for c in zip(*[zs(SIM[x]) for x in likes])]
    pen = [max(c) for c in zip(*[[max(0, v) for v in zs(SIM[x])] for x in p['dislikes']])] if p['dislikes'] else [0] * len(lab_ids)
    sc = [a - b for a, b in zip(zl, pen)]
    emb = [lab_ids[i] for i in sorted(range(len(sc)), key=lambda i: -sc[i])]
    dic = pipeline.dict_ranking(cat, p['likes'], p['dislikes'], p['norm'])
    r['rank'] = pipeline.rrf(dic, emb) if dic else emb
    r['dict'] = dic
    r['emb'] = emb
    reasons = list(p['flags'])
    for x in p['likes']:
        if not p['phrase_concepts'].get(x) and max(SIM[x]) < TH['phrase']:
            reasons.append('unmatched_phrase')
    if not dic and max(SIM[p['norm']]) < TH['query']:
        reasons.append('weak_query')
    r['reasons'] = sorted(set(reasons)); r['routed'] = bool(reasons)
    return r

def rel(l, q): return any(prim[l] & set(g) for g in q['pos'])
def viol(l, q): return bool(prim[l] & set(q['neg'])) and not rel(l, q)
def m5(top, q):
    top = top[:K]
    m = {'p5': sum(rel(l, q) for l in top) / K}
    m['viol'] = float(any(viol(l, q) for l in top)) if q['neg'] else 0.0
    m['cover'] = float(all(any(prim[l] & set(g) for l in top) for g in q['pos'])) if len(q['pos']) > 1 else 1.0
    m['ok'] = float(m['p5'] >= 0.6 and not m['viol'] and m['cover'])
    return m

def evaluate(Q, name):
    res = {'A': {}, 'Pdict': {}, 'Pnoroute': {}, 'P': {}}
    for q in Q:
        a = [r['id'] for r in cat.search(q['text'])]
        res['A'][q['id']] = {'rank': a}
        res['P'][q['id']] = run_P(q)
    print(f'\n===== {name} ({len(Q)}개) =====')
    search = [q for q in Q if q['intent'] == 'search']
    if search:
        rows = {}
        for q in search:
            r = res['P'][q['id']]
            pm = m5(r['rank'], q) if r['rank'] else {'p5': 0, 'viol': 0, 'cover': 0, 'ok': 0}   # 의도 오분류 = 실패
            am = m5(res['A'][q['id']]['rank'], q)
            dm = m5(r['dict'], q) if r['rank'] else pm
            rows[q['id']] = (am, dm, pm, r['routed'], q['type'], bool(q['neg']))
        n = len(search)
        avg = lambda i, k, f=lambda x: True: round(mean([v[i][k] for v in rows.values() if f(v)]), 2)
        print(f'[검색 질의 {n}개]  P@5 / 싫은주제 혼입 / 성공률')
        for lab, i in [('A 현재 앱', 0), ('P-사전+해석(임베딩 없음)', 1), ('P-제안(라우팅 무시)', 2)]:
            neg = [v for v in rows.values() if v[5]]
            print(f'  {lab:<26} {avg(i,"p5")}  /  {round(mean([v[i]["viol"] for v in neg]),2) if neg else "-"}  /  {avg(i,"ok")}')
        routed = [k for k, v in rows.items() if v[3]]
        non = [v for v in rows.values() if not v[3]]
        print(f'  제안 파이프라인 라우팅(Gemini 호출) {len(routed)}/{n} = {len(routed)/n:.0%}')
        print(f'    라우팅 안 한 질의의 성공률 {mean([v[2]["ok"] for v in non]):.2f}  (A는 같은 질의에서 {mean([v[0]["ok"] for v in non]):.2f})' if non else '')
        print(f'    조용한 실패(라우팅 안 했는데 틀림) P {sum(1 for v in non if not v[2]["ok"])}/{n}  vs  A {sum(1 for v in rows.values() if not v[0]["ok"])}/{n}')
        print(f'    성공률 하한(라우팅=실패) {sum(v[2]["ok"] for v in non)/n:.2f} ~ 상한(라우팅=성공) {(sum(v[2]["ok"] for v in non)+len(routed))/n:.2f}  vs  A {mean([v[0]["ok"] for v in rows.values()]):.2f}')
        print('  유형별 성공률 A | P(라우팅 안 한 것만) | 라우팅 비율')
        for t in sorted({v[4] for v in rows.values()}):
            vs = [v for v in rows.values() if v[4] == t]; nn = [v for v in vs if not v[3]]
            print(f'    {t:<14} A {mean([v[0]["ok"] for v in vs]):.2f} | P {mean([v[2]["ok"] for v in nn]) if nn else float("nan"):.2f} ({len(nn)}건) | 라우팅 {1-len(nn)/len(vs):.0%}')
    non_search = [q for q in Q if q['intent'] != 'search']
    if non_search:
        print('[검색이 아닌 의도]  정답 의도 | A가 결과를 보여줌(오답) | P 정답 / 라우팅 / 오답')
        for it in ['too_broad', 'career', 'out_of_scope', 'nonsense']:
            qs = [q for q in non_search if q['intent'] == it]
            if not qs: continue
            a_bad = sum(1 for q in qs if res['A'][q['id']]['rank'])
            pr = [res['P'][q['id']] for q in qs]
            ok = sum(1 for r in pr if not r['routed'] and r['intent'] == it)
            rt = sum(1 for r in pr if r['routed'])
            print(f'    {it:<13} {len(qs)}개 | A 오답 {a_bad} | P 정답 {ok} / 라우팅 {rt} / 오답 {len(qs)-ok-rt}')
    return res

R_dev = evaluate(dev, '개발용 질의 (임계값을 정한 세트 — 참고용)')
R_test = evaluate(test, '시험용 질의 (임계값 고정 후 한 번만 평가)')
json.dump({'dev': {k: {q: {kk: vv for kk, vv in v.items() if kk != 'emb'} for q, v in d.items()} for k, d in R_dev.items()},
           'test': {k: {q: {kk: vv for kk, vv in v.items() if kk != 'emb'} for q, v in d.items()} for k, d in R_test.items()}},
          open(D + 'V2_results.json', 'w', encoding='utf-8'), ensure_ascii=False)
