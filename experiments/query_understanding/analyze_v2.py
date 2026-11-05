"""V2 사후 분석: (1) 정답이 1~2곳뿐인 질의를 위한 보정 지표, (2) 질의 단위 부트스트랩. 저장소 루트에서 python3 -I 로 실행."""
import json, random
D = 'experiments/query_understanding/'
R = json.load(open(D + 'V2_results.json', encoding='utf-8'))['test']
T = [q for q in json.load(open(D + 'queries_test.json', encoding='utf-8')) if q['intent'] == 'search']
labs = [json.loads(l) for l in open('data/lab_profiles.jsonl', encoding='utf-8')]
prim = {p['lab_id']: {t['concept'] for t in p['topics'] if t.get('weight', 'primary') == 'primary'} for p in labs if p['status'] != 'insufficient'}
rel = lambda l, q: any(prim[l] & set(g) for g in q['pos'])
viol = lambda l, q: bool(prim[l] & set(q['neg'])) and not rel(l, q)
def ok(top, q, corrected):
    top = (top or [])[:5]
    n_rel = sum(1 for l in prim if rel(l, q))
    need = min(0.6, n_rel / 5) if corrected else 0.6          # 정답이 1~2곳이면 그만큼만 찾으면 성공
    p5 = sum(rel(l, q) for l in top) / 5
    cover = all(any(prim[l] & set(g) for l in top) for g in q['pos']) if len(q['pos']) > 1 else True
    return float(p5 >= need - 1e-9 and cover and not (q['neg'] and any(viol(l, q) for l in top)))
sys = {'A': lambda q: R['A'][q['id']]['rank'], 'P-사전+해석': lambda q: R['P'][q['id']].get('dict'), 'P-제안': lambda q: R['P'][q['id']]['rank']}
for corrected in (False, True):
    print('\n[보정 지표]' if corrected else '\n[사전 지표: P@5 ≥ 0.6]')
    sc = {k: [ok(f(q), q, corrected) for q in T] for k, f in sys.items()}
    routed = [R['P'][q['id']]['routed'] for q in T]
    n = len(T)
    for k, v in sc.items(): print(f'  {k:<12} 성공률 {sum(v)/n:.2f}')
    p = sc['P-제안']
    non = [i for i in range(n) if not routed[i]]
    print(f'  제안: 라우팅 {sum(routed)}/{n}, 안 한 질의 성공률 {sum(p[i] for i in non)/len(non):.2f} (같은 질의 A {sum(sc["A"][i] for i in non)/len(non):.2f}), 조용한 실패 P {sum(1-p[i] for i in non):.0f} vs A {sum(1-x for x in sc["A"]):.0f}')
    print(f'  성공률 하한~상한(라우팅을 실패~성공으로 가정): {sum(p[i] for i in non)/n:.2f} ~ {(sum(p[i] for i in non)+sum(routed))/n:.2f}')
    w = sum(1 for i in range(n) if p[i] > sc['A'][i]); l = sum(1 for i in range(n) if p[i] < sc['A'][i])
    print(f'  질의별 P vs A: P가 이김 {w}, A가 이김 {l}, 같음 {n-w-l}')
    rnd = random.Random(0); diffs = []
    for _ in range(3000):
        idx = [rnd.randrange(n) for _ in range(n)]
        diffs.append(sum(p[i] - sc['A'][i] for i in idx) / n)
    diffs.sort(); print(f'  성공률 차이(P−A) 95% 구간 [{diffs[75]:+.2f}, {diffs[2924]:+.2f}] (질의 부트스트랩)')
