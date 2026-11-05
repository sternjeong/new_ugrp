"""실험 2: 가짜 사용자 피드백(최고 1·최악 1)으로 순서를 조정할 때 무관한 과목이 목록에 들어오는지 시뮬레이션."""
import json, random, statistics, itertools, sys
from common import load, ndcg, HERE

cands = load()
labs = sorted(cands)
GATE_K = json.load(open(HERE / 'results/gate_result.json', encoding='utf-8'))['final']
assert GATE_K.startswith('rank<='), GATE_K
GATE = int(GATE_K.split('<=')[1])          # 사전 등록 규칙으로 고른 관문(기본 rank<=8)
A, REPS = 10, 200
rng = random.Random(20261011)


def draw_votes(display, n_users, noise, mal):
    """display: [(cid,label)...]. 반환: {cid: [best표, worst표]}"""
    votes = {cid: [0, 0] for cid, _ in display}
    for _ in range(n_users):
        labs_ = [l for _, l in display]
        hi, lo = max(labs_), min(labs_)
        best = rng.choice([c for c, l in display if l == hi]); worst_pool = [c for c, l in display if l == lo and c != best]
        worst = rng.choice(worst_pool) if worst_pool else rng.choice([c for c, _ in display if c != best])
        if rng.random() < noise:
            best, worst = rng.sample([c for c, _ in display], 2)
        elif rng.random() < mal:
            best, worst = worst, best
        votes[best][0] += 1; votes[worst][1] += 1
    return votes


def shifted(order, votes, n, delta, k):
    """order: 기본 순서의 cid 목록. 이동만큼 위/아래로 옮긴 새 순서."""
    key = {}
    for pos, cid in enumerate(order):
        b, w = votes.get(cid, (0, 0))
        s = A * (b - w) / (n + k)
        s = max(-delta, min(delta, round(s)))
        key[cid] = (pos - s, pos)
    return sorted(order, key=lambda c: key[c])


def simulate(lab, method, n, noise, mal, G):
    rows = cands[lab]; lab_of = {r['cid']: r['label'] for r in rows}; pool = [r['label'] for r in rows]
    base_order = [r['cid'] for r in rows]                 # 기본 순위(피드백과 무관)
    if method == 'M0':
        final = base_order[:10]
    elif method == 'M1':                                   # 관문 없음, 항상 10개 채움, 상한·완충 없음
        disp = [(c, lab_of[c]) for c in base_order[:10]]
        v = draw_votes(disp, n, noise, mal)
        final = shifted(base_order, v, n, 10 ** 6, 0)[:10]
    else:
        gated = base_order[:G]                             # 관문 통과 목록(기본 순위로 고정)
        disp = [(c, lab_of[c]) for c in gated[:10]]
        v = draw_votes(disp, n, noise, mal)
        delta, k = {'M2': (10 ** 6, 0), 'M3': (3, 0), 'M4': (3, 10), 'M5': (3, 10)}[method]
        final = shifted(gated, v, n, delta, k)
        if method == 'M5':                                 # 강한 부정 합의면 제외(길이만 줄고 새 항목은 안 들어옴)
            final = [c for c in final if not (v[c][1] >= max(3, 0.5 * n) and v[c][1] > v[c][0])]
        assert set(final) <= set(gated)                    # 구조 검사: 관문 밖 항목이 들어오지 않는다
    L = [lab_of[c] for c in final]
    entrants = [c for c in final if c not in base_order[:10]] if method != 'M0' else []
    return {'ndcg5': ndcg(L, pool, 5), 'ndcg10': ndcg(L, pool, 10), 'len': len(L), 'zero': sum(x == 0 for x in L) / len(L) if L else 0.0,
            'entrants': len(entrants), 'entrant_zero': sum(lab_of[c] == 0 for c in entrants)}


def run(G, conds):
    out = {}
    for (n, noise, mal), m in itertools.product(conds, ['M0', 'M1', 'M2', 'M3', 'M4', 'M5']):
        acc = {k: [] for k in ('ndcg5', 'ndcg10', 'len', 'zero', 'entrants', 'entrant_zero')}
        for lab in labs:
            reps = [simulate(lab, m, n, noise, mal, G) for _ in range(1 if m == 'M0' else REPS)]
            for k in acc: acc[k].append(statistics.mean(r[k] for r in reps))
        ent = sum(acc['entrants']); entz = sum(acc['entrant_zero'])
        out[f'{m}|n={n}|noise={noise}|mal={mal}'] = {'ndcg5': statistics.mean(acc['ndcg5']), 'ndcg10': statistics.mean(acc['ndcg10']),
            'len': statistics.mean(acc['len']), 'zero': statistics.mean(acc['zero']), 'entrants_per_lab': ent / len(labs),
            'entrant_zero_rate': (entz / ent) if ent else None}
    return out


conds = list(itertools.product((5, 10, 20, 40), (0.0, 0.2, 0.4), (0.0, 0.1)))
main = run(GATE, conds)
sens = {g: run(g, [(20, 0.2, 0.0), (20, 0.0, 0.0)]) for g in (5, 10)}

# 표적 시나리오: 전원이 기본 10위 항목을 '최악', 1위를 '최고'로 투표(합의)
def targeted(method, G, n=20):
    res = []
    for lab in labs:
        rows = cands[lab]; base = [r['cid'] for r in rows]; lab_of = {r['cid']: r['label'] for r in rows}
        if lab_of[base[10]] != 0: continue                 # 11위가 무관(0점)인 연구실만
        gated = base[:G] if method != 'M1' else base
        v = {c: [0, 0] for c in base}; v[base[0]][0] = n; v[base[9]][1] = n
        if method == 'M1': final = shifted(base, v, n, 10 ** 6, 0)[:10]
        else: final = shifted(gated, v, n, 3, 10)
        res.append(base[10] in final[:10])
    return sum(res), len(res)
tgt = {m: targeted(m, GATE) for m in ('M1', 'M4')}

# ---- 판정 ----
g = lambda m, n, no, ma: main[f'{m}|n={n}|noise={no}|mal={ma}']
c3 = {n: {m: g(m, n, 0.2, 0.0)['ndcg5'] - g('M0', n, 0.2, 0.0)['ndcg5'] for m in ('M3', 'M4')} for n in (10, 20, 40)}
crit = {}
crit['1_구조검사(관문 밖 유입 없음, M5 유입 0)'] = all(main[k]['entrants_per_lab'] == 0 for k in main if k.split('|')[0] in ('M2', 'M3', 'M4', 'M5'))
m1_ez = [v['entrant_zero_rate'] for k, v in main.items() if k.startswith('M1|') and v['entrant_zero_rate'] is not None]
crit['2_순진방식 유입 항목의 0점 비율(참고)'] = f"M1 평균 {statistics.mean(m1_ez):.0%}, 관문 방식은 유입 0건"
crit['3_잡음0.2 nDCG@5가 M0 이상(M3 또는 M4, n>=10)'] = all(max(c3[n].values()) >= -0.01 for n in c3)
c4 = [(k, v['ndcg5'] - main['M0' + k[2:].replace(k[2:], '|n=' + k.split('|')[1][2:] + '|' + '|'.join(k.split('|')[2:]))]['ndcg5']) for k, v in main.items() if k.startswith('M4|') and (('noise=0.4' in k) or ('mal=0.1' in k))] if False else None
worst4 = min(g('M4', n, no, ma)['ndcg5'] - g('M0', n, no, ma)['ndcg5'] for n, no, ma in conds if no == 0.4 or ma == 0.1)
crit['4_잡음0.4·악의0.1에서 M4가 M0보다 0.03 넘게 안 나쁨'] = worst4 >= -0.03
crit['5_관문 목록 3개 이상 연구실 >=90%'] = json.load(open(HERE / 'results/gate_result.json', encoding='utf-8'))['final_metrics']['cover3'] >= 0.9
json.dump({'gate': GATE_K, 'main': main, 'sensitivity_gate': {str(k): v for k, v in sens.items()}, 'targeted_rank11_enters': tgt,
           'criteria': crit, 'c3_diffs': c3, 'worst_M4_minus_M0': worst4}, open(HERE / 'results/feedback_result.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

L = [f'관문 = {GATE_K}', '', '조건(잡음 0.2·악의 0)별 nDCG@5 / 길이 / 새로 들어온 항목 수(연구실당) / 그 중 0점 비율']
for n in (5, 10, 20, 40):
    L.append(f'  사용자 {n}명')
    for m in ('M0', 'M1', 'M2', 'M3', 'M4', 'M5'):
        v = g(m, n, 0.2, 0.0); ez = '-' if v['entrant_zero_rate'] is None else f"{v['entrant_zero_rate']:.0%}"
        L.append(f"    {m}: nDCG@5 {v['ndcg5']:.3f}  nDCG@10 {v['ndcg10']:.3f}  길이 {v['len']:.1f}  0점 {v['zero']:.0%}  유입 {v['entrants_per_lab']:.2f}건 (0점 {ez})")
L += ['', '표적 시나리오(전원이 10위를 최악, 1위를 최고로 투표; 11위가 0점인 연구실만): 11위가 상위 10에 들어온 연구실 수'] + [f"  {m}: {a}/{b}" for m, (a, b) in tgt.items()]
L += ['', '판정'] + [f"  {k}: {v}" for k, v in crit.items()] + [f"  (기준3 M3/M4 차이 {c3}; 기준4 최악 차이 {worst4:+.3f})"]
(HERE / 'results/feedback_table.txt').write_text('\n'.join(L), encoding='utf-8')
print('\n'.join(L))
