"""실험 3: 본 목록(상위 8) + 탐색 칸. 관문 밖 후보를 소수 칸에서만 노출하고 '예/아니오' 응답이 쌓이면 승격한다."""
import json, math, random, statistics, itertools
from common import load, HERE

cands = load(); labs = sorted(cands)
G, REPS, CHECK = 8, 100, (5, 10, 20, 40, 80, 160)
P_YES = {2: 0.9, 1: 0.5, 0: 0.1}
Z = 1.2816  # 90% 단측
rng = random.Random(7)


def wilson(y, n):
    if n == 0: return 0.0, 1.0
    p = y / n; d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d; h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return c - h, c + h


def pool_of(lab, kind):
    rows = [r for r in cands[lab] if r['rank'] > G]
    if kind == 'E': return [r for r in rows if r['rank'] <= 20 and r['shared'] >= 1]
    if kind == 'E2': return [r for r in rows if r['shared'] >= 1]
    return rows


def answer(label, noise, mal):
    yes = rng.random() < P_YES[label]
    if rng.random() < noise: yes = rng.random() < 0.5
    elif rng.random() < mal: yes = not yes
    return yes


def run_lab(lab, kind, S, policy, noise, mal):
    pool = pool_of(lab, kind); core = [r for r in cands[lab] if r['rank'] <= G]
    st = {r['cid']: [0, 0, r['label']] for r in pool}      # 예, 응답, 라벨
    active = set(st); promoted, retired = [], []
    bad_imp = imp = 0; snaps = {}
    for t in range(1, max(CHECK) + 1):
        if active:
            ids = sorted(active)
            if policy == 'random': shown = rng.sample(ids, min(S, len(ids)))
            else:
                key = {c: (st[c][0] + 1) / (st[c][1] + 2) + 0.6 / math.sqrt(st[c][1] + 1) + rng.random() * 1e-6 for c in ids}
                shown = sorted(ids, key=lambda c: -key[c])[:S]
            for c in shown:
                y = answer(st[c][2], noise, mal); st[c][0] += y; st[c][1] += 1
                imp += 1; bad_imp += st[c][2] == 0
                lo, hi = wilson(st[c][0], st[c][1])
                if st[c][1] >= 6 and lo >= 0.5: promoted.append(c); active.discard(c)
                elif st[c][1] >= 5 and hi < 0.4: retired.append(c); active.discard(c)
        if t in CHECK:
            pl = [st[c][2] for c in promoted]; final = [r['label'] for r in core] + pl
            two_pool = sum(v[2] == 2 for v in st.values()); two_all = sum(r['label'] == 2 for r in cands[lab] if r['rank'] > G)
            snaps[t] = {'prom': len(pl), 'prom_zero': sum(x == 0 for x in pl), 'prom_rel': sum(x >= 1 for x in pl), 'prom_two': sum(x == 2 for x in pl),
                        'two_pool': two_pool, 'two_all': two_all, 'bad_imp': bad_imp, 'imp': imp,
                        'final_len': len(final), 'final_zero': sum(x == 0 for x in final), 'final_two': sum(x == 2 for x in final),
                        'core_two': sum(r['label'] == 2 for r in core), 'retired_good': sum(st[c][2] >= 1 for c in retired), 'retired': len(retired)}
    return snaps


def aggregate(kind, S, policy, noise, mal):
    tot = {T: {} for T in CHECK}
    for lab in labs:
        for _ in range(REPS):
            for T, s in run_lab(lab, kind, S, policy, noise, mal).items():
                for k, v in s.items(): tot[T][k] = tot[T].get(k, 0) + v
    n = len(labs) * REPS; out = {}
    for T, s in tot.items():
        out[T] = {'promoted_per_lab': s['prom'] / n, 'prom_zero_rate': s['prom_zero'] / s['prom'] if s['prom'] else None,
                  'prom_rel_rate': s['prom_rel'] / s['prom'] if s['prom'] else None,
                  'found_two_in_pool': s['prom_two'] / s['two_pool'] if s['two_pool'] else None,
                  'found_two_of_outside': s['prom_two'] / s['two_all'] if s['two_all'] else None,
                  'bad_impression_rate': s['bad_imp'] / s['imp'] if s['imp'] else None,
                  'final_len': s['final_len'] / n, 'final_zero_rate': s['final_zero'] / s['final_len'],
                  'final_two_per_lab': s['final_two'] / n, 'core_two_per_lab': s['core_two'] / n,
                  'retired_good_per_lab': s['retired_good'] / n}
    return out


def main():
    res = {}
    for kind in ('E',):
        for S, policy, noise, mal in itertools.product((1, 2), ('random', 'ucb'), (0.0, 0.2, 0.4), (0.0, 0.1)):
            res[f'{kind}|S={S}|{policy}|noise={noise}|mal={mal}'] = aggregate(kind, S, policy, noise, mal)
    for kind in ('E2', 'E3'):
        for policy in ('random', 'ucb'):
            res[f'{kind}|S=2|{policy}|noise=0.2|mal=0.0'] = aggregate(kind, 2, policy, 0.2, 0.0)

    g = lambda k, T: res[k][T]
    # ---- 판정 ----
    c1 = [g(f'E|S={S}|{p}|noise={n}|mal=0.0', T)['prom_zero_rate'] for S in (1, 2) for p in ('random', 'ucb') for n in (0.0, 0.2) for T in (40, 80, 160)]
    crit = {'1_승격 정확도(0점 비율<=15%)': (max(x for x in c1 if x is not None), all(x is not None and x <= 0.15 for x in c1)),
            '2_발견(풀의 핵심 중 승격>=40%, T=160,S=2,잡음.2)': tuple(g(f'E|S=2|{p}|noise=0.2|mal=0.0', 160)['found_two_in_pool'] for p in ('random', 'ucb'))}
    crit['2_발견(풀의 핵심 중 승격>=40%, T=160,S=2,잡음.2)'] = (crit['2_발견(풀의 핵심 중 승격>=40%, T=160,S=2,잡음.2)'], all(x >= 0.4 for x in crit['2_발견(풀의 핵심 중 승격>=40%, T=160,S=2,잡음.2)']))
    u, r_ = g('E|S=2|ucb|noise=0.2|mal=0.0', 80)['bad_impression_rate'], g('E|S=2|random|noise=0.2|mal=0.0', 80)['bad_impression_rate']
    crit['3_노출 비용(UCB 0점 노출 <= 무작위의 90%)'] = ((round(u, 3), round(r_, 3)), u <= 0.9 * r_)
    f = [g(f'E|S=2|{p}|noise=0.2|mal=0.0', 160) for p in ('random', 'ucb')]
    crit['4_최종 목록(0점 비율<=26% & 핵심 수 증가)'] = (tuple((round(x['final_zero_rate'], 3), round(x['final_two_per_lab'], 2), round(x['core_two_per_lab'], 2)) for x in f),
                                               all(x['final_zero_rate'] <= 0.26 and x['final_two_per_lab'] > x['core_two_per_lab'] for x in f))
    c5 = [g(f'E|S={S}|{p}|noise={n}|mal={m}', T)['prom_zero_rate'] for S in (1, 2) for p in ('random', 'ucb') for n, m in ((0.4, 0.0), (0.0, 0.1), (0.4, 0.1)) for T in (80, 160)]
    crit['5_강건성(잡음.4/악의.1에서 승격 0점 비율<=25%)'] = (max(x for x in c5 if x is not None), all(x is not None and x <= 0.25 for x in c5))
    json.dump({'results': res, 'criteria': {k: [v[0], v[1]] for k, v in crit.items()}}, open(HERE / 'results/explore_result.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)

    fmt = lambda x: '-' if x is None else f'{x:.0%}'
    L = ['잡음 0.2, 악의 0, 탐색 풀 E(9~20위 & 공유 개념) -- 연구실당 응답 사용자 수 T별', '']
    for S in (1, 2):
        for p in ('random', 'ucb'):
            L.append(f'S={S} {p}')
            L.append(f"  {'T':>4} {'승격(건/연구실)':>14} {'승격중 0점':>10} {'승격중 >=1':>10} {'풀 핵심 발견':>11} {'관문밖 핵심 발견':>14} {'무관 노출':>8} {'최종 0점':>8} {'핵심 수(본→최종)':>16}")
            for T in CHECK:
                x = g(f'E|S={S}|{p}|noise=0.2|mal=0.0', T)
                L.append(f"  {T:>4} {x['promoted_per_lab']:14.2f} {fmt(x['prom_zero_rate']):>10} {fmt(x['prom_rel_rate']):>10} {fmt(x['found_two_in_pool']):>11} {fmt(x['found_two_of_outside']):>14} {fmt(x['bad_impression_rate']):>8} {fmt(x['final_zero_rate']):>8} {x['core_two_per_lab']:.2f}→{x['final_two_per_lab']:.2f}".rstrip())
    L += ['', '탐색 풀 민감도 (S=2, 잡음 0.2, T=160)']
    for kind in ('E', 'E2', 'E3'):
        for p in ('random', 'ucb'):
            x = g(f'{kind}|S=2|{p}|noise=0.2|mal=0.0', 160)
            L.append(f"  {kind:3} {p:6} 승격 {x['promoted_per_lab']:.2f}건 0점 {fmt(x['prom_zero_rate'])} 풀 핵심 발견 {fmt(x['found_two_in_pool'])} 관문밖 핵심 발견 {fmt(x['found_two_of_outside'])} 무관 노출 {fmt(x['bad_impression_rate'])}")
    L += ['', '잡음·악의 강건성 (S=2, UCB, T=160)']
    for n, m in ((0.0, 0.0), (0.2, 0.0), (0.4, 0.0), (0.0, 0.1), (0.4, 0.1)):
        x = g(f'E|S=2|ucb|noise={n}|mal={m}', 160)
        L.append(f"  잡음 {n} 악의 {m}: 승격 {x['promoted_per_lab']:.2f}건 0점 {fmt(x['prom_zero_rate'])} 풀 핵심 발견 {fmt(x['found_two_in_pool'])}")
    L += ['', '판정'] + [f"  {k}: {'통과' if v[1] else '실패'}  {v[0]}" for k, v in crit.items()]
    (HERE / 'results/explore_table.txt').write_text('\n'.join(L), encoding='utf-8')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
