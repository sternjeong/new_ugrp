"""실험 4: 비슷한 연구실끼리 같은 과목의 '예/아니오' 응답을 부분 공유하면 적은 응답으로도 발견이 일어나는가."""
import json, math, random, statistics, itertools
from collections import defaultdict
from common import load, ROOT, HERE

cands = load(); labs = sorted(cands)
G, REPS, VS = 8, 100, (40, 100, 200, 400, 800)
SETS = {'선명': {2: 0.9, 1: 0.5, 0: 0.1}, '보통': {2: 0.75, 1: 0.5, 0: 0.25}, '흐림': {2: 0.65, 1: 0.5, 0: 0.35}}
NOISE, S, Z, SIM_MIN, N2_W = 0.2, 2, 1.2816, 0.2, 0.5
rng = random.Random(11)

prim = {}
for line in open(ROOT / 'data/lab_profiles.jsonl', encoding='utf-8'):
    p = json.loads(line)
    prim[p['lab_id']] = {t['concept'] for t in p.get('topics', []) if t.get('weight') == 'primary'}
sim = {}
for a, b in itertools.permutations(labs, 2):
    u = prim[a] | prim[b]; j = len(prim[a] & prim[b]) / len(u) if u else 0.0
    sim[(a, b)] = j if j >= SIM_MIN else 0.0
pool = {l: {r['cid']: r for r in cands[l] if r['rank'] > G and r['rank'] <= 20 and r['shared'] >= 1} for l in labs}
core2 = {l: sum(r['label'] == 2 for r in cands[l] if r['rank'] <= G) for l in labs}
core_n = {l: sum(1 for r in cands[l] if r['rank'] <= G) for l in labs}
core_zero = {l: sum(r['label'] == 0 for r in cands[l] if r['rank'] <= G) for l in labs}


def neighbors(method):
    """(lab, cid) -> [(다른 lab, 가중치)]  (그 lab 풀에도 cid가 있는 경우만)"""
    nb = defaultdict(list)
    if method == 'N0': return nb
    for l in labs:
        for c in pool[l]:
            for m in labs:
                if m != l and c in pool[m]:
                    w = N2_W if method == 'N2' else sim[(l, m)]
                    if w > 0: nb[(l, c)].append((m, w))
    return nb


def wilson(y, n):
    if n <= 0: return 0.0, 1.0
    p = min(1.0, y / n); d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d; h = Z * math.sqrt(max(p * (1 - p) / n + Z * Z / (4 * n * n), 0)) / d
    return c - h, c + h


def data_stats():
    nb = neighbors('N1'); items = [(l, c) for l in labs for c in pool[l]]
    with_nb = sum(1 for k in items if nb[k]); deg = statistics.mean(len(nb[k]) for k in items)
    agree = defaultdict(list)
    for (l, c), lst in nb.items():
        for m, w in lst: agree[cands_label[(l, c)]].append(cands_label[(m, c)])
    fid = {k: (sum(x >= 1 for x in v) / len(v), sum(x == 2 for x in v) / len(v), len(v)) for k, v in agree.items()}
    return {'items': len(items), 'items_with_neighbor': with_nb, 'mean_neighbors': deg, 'fidelity_by_label_of_source': fid}


cands_label = {(l, r['cid']): r['label'] for l in labs for r in cands[l]}


def one_rep(method, p_yes, nbm, guard):
    own = {(l, c): [0.0, 0] for l in labs for c in pool[l]}
    active = {l: set(pool[l]) for l in labs}; prom = {l: [] for l in labs}; ret = {l: [] for l in labs}; pure = {l: [] for l in labs}
    bad = imp = 0; snaps = {}

    def eff(l, c):
        y, n = own[(l, c)][0], float(own[(l, c)][1])
        for m, w in nbm[(l, c)]:
            o = own[(m, c)]; y += w * o[0]; n += w * o[1]
        return y, n

    def check(l, c):
        if c not in active[l]: return
        y, n = eff(l, c); lo, hi = wilson(y, n)
        if n >= 6 and lo >= 0.5 and (not guard or own[(l, c)][1] >= 2):
            prom[l].append(c); active[l].discard(c)
            if own[(l, c)][1] == 0: pure[l].append(c)
        elif n >= 5 and hi < 0.4:
            ret[l].append(c); active[l].discard(c)

    for v in range(1, max(VS) + 1):
        l = rng.choice(labs); ids = sorted(active[l])
        if ids:
            key = {}
            for c in ids:
                y, n = eff(l, c); key[c] = (y + 1) / (n + 2) + 0.6 / math.sqrt(n + 1) + rng.random() * 1e-6
            for c in sorted(ids, key=lambda c: -key[c])[:S]:
                lab_c = cands_label[(l, c)]
                yes = rng.random() < p_yes[lab_c]
                if rng.random() < NOISE: yes = rng.random() < 0.5
                own[(l, c)][0] += yes; own[(l, c)][1] += 1; imp += 1; bad += lab_c == 0
                check(l, c)
                for m in nbm_rev[method].get((l, c), ()): check(m, c)   # 이 응답이 영향 주는 다른 연구실 항목
        if v in VS:
            snaps[v] = {'prom': sum(len(prom[x]) for x in labs), 'prom_zero': sum(cands_label[(x, c)] == 0 for x in labs for c in prom[x]),
                        'prom_rel': sum(cands_label[(x, c)] >= 1 for x in labs for c in prom[x]),
                        'prom_two': sum(cands_label[(x, c)] == 2 for x in labs for c in prom[x]),
                        'two_pool': sum(r['label'] == 2 for x in labs for r in pool[x].values()),
                        'pure': sum(len(pure[x]) for x in labs), 'pure_zero': sum(cands_label[(x, c)] == 0 for x in labs for c in pure[x]),
                        'bad': bad, 'imp': imp,
                        'final_len': sum(core_n[x] + len(prom[x]) for x in labs),
                        'final_zero': sum(core_zero[x] + sum(cands_label[(x, c)] == 0 for c in prom[x]) for x in labs),
                        'final_two': sum(core2[x] + sum(cands_label[(x, c)] == 2 for c in prom[x]) for x in labs)}
    return snaps


nbm_rev = {}
def build_rev(method):
    nb = neighbors(method); rev = defaultdict(list)
    for (l, c), lst in nb.items():
        for m, w in lst: rev[(m, c)].append(l)       # (m,c)의 응답이 (l,c)의 유효 응답에 들어감
    nbm_rev[method] = rev
    return nb


def aggregate(method, pname, guard):
    nb = build_rev(method) if method != 'N0' else defaultdict(list)
    if method == 'N0': nbm_rev['N0'] = {}
    tot = {V: defaultdict(float) for V in VS}
    for _ in range(REPS):
        for V, s in one_rep(method, SETS[pname], nb, guard).items():
            for k, x in s.items(): tot[V][k] += x
    out = {}
    for V, s in tot.items():
        out[V] = {'prom_per_lab': s['prom'] / REPS / len(labs), 'prom_zero': s['prom_zero'] / s['prom'] if s['prom'] else None,
                  'prom_rel': s['prom_rel'] / s['prom'] if s['prom'] else None, 'found_two': s['prom_two'] / s['two_pool'],
                  'pure_per_lab': s['pure'] / REPS / len(labs), 'pure_zero': s['pure_zero'] / s['pure'] if s['pure'] else None,
                  'bad_imp': s['bad'] / s['imp'], 'final_zero': s['final_zero'] / s['final_len'],
                  'final_two_per_lab': s['final_two'] / REPS / len(labs)}
    return out


def main():
    ds = data_stats()
    res = {}
    for pname in SETS:
        for name, (method, guard) in {'N0': ('N0', False), 'N1': ('N1', False), 'N1g': ('N1', True), 'N2': ('N2', False)}.items():
            res[f'{name}|{pname}'] = aggregate(method, pname, guard)
    g = lambda m, p, V: res[f'{m}|{p}'][V]
    crit = {}
    crit['1_효과(V=200, N1g 풀 핵심 발견 - N0 >= 15%p)'] = {p: (round(g('N1g', p, 200)['found_two'], 3), round(g('N0', p, 200)['found_two'], 3)) for p in ('선명', '보통')}
    crit['1_효과(V=200, N1g 풀 핵심 발견 - N0 >= 15%p)']['ok'] = all(g('N1g', p, 200)['found_two'] - g('N0', p, 200)['found_two'] >= 0.15 for p in ('선명', '보통'))
    z = lambda m, p, V: g(m, p, V)['prom_zero'] if g(m, p, V)['prom_zero'] is not None else 0.0
    crit['2_정확도(V>=200, N1g 승격 0점<=15%)'] = {'max': round(max(z('N1g', p, V) for p in ('선명', '보통') for V in (200, 400, 800)), 3)}
    crit['2_정확도(V>=200, N1g 승격 0점<=15%)']['ok'] = crit['2_정확도(V>=200, N1g 승격 0점<=15%)']['max'] <= 0.15
    crit['3_유사도 가중(V=400, N1g 0점 <= N2 0점)'] = {p: (round(z('N1g', p, 400), 3), round(z('N2', p, 400), 3)) for p in ('선명', '보통')}
    crit['3_유사도 가중(V=400, N1g 0점 <= N2 0점)']['ok'] = all(z('N1g', p, 400) <= z('N2', p, 400) for p in ('선명', '보통'))
    pz = lambda p: g('N1', p, 400)['pure_zero']
    crit['4_순수 전이(V=400, N1 자기응답 없이 승격된 것의 0점<=20%)'] = {p: (None if pz(p) is None else round(pz(p), 3), round(g('N1', p, 400)['pure_per_lab'], 2)) for p in ('선명', '보통')}
    crit['4_순수 전이(V=400, N1 자기응답 없이 승격된 것의 0점<=20%)']['ok'] = all((pz(p) or 0) <= 0.20 for p in ('선명', '보통'))
    crit['5_적은 응답(V=100, 선명, N1g 풀 핵심 발견>=25%)'] = {'N1g': round(g('N1g', '선명', 100)['found_two'], 3), 'N0': round(g('N0', '선명', 100)['found_two'], 3)}
    crit['5_적은 응답(V=100, 선명, N1g 풀 핵심 발견>=25%)']['ok'] = g('N1g', '선명', 100)['found_two'] >= 0.25
    json.dump({'data': {k: v for k, v in ds.items() if k != 'fidelity_by_label_of_source'} | {'fidelity': {str(k): v for k, v in ds['fidelity_by_label_of_source'].items()}},
               'results': {k: {str(V): x for V, x in v.items()} for k, v in res.items()}, 'criteria': crit},
              open(HERE / 'results/propagate_result.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    f = lambda x: '-' if x is None else f'{x:.0%}'
    L = [f"데이터: 탐색 풀 항목 {ds['items']}개 중 다른 연구실 풀에도 같은 과목이 있는(유사도>=0.2) 항목 {ds['items_with_neighbor']}개, 항목당 이웃 평균 {ds['mean_neighbors']:.1f}곳",
         '전이 충실도(출처 연구실의 라벨별: 이웃 연구실에서 >=1점 비율 / 2점 비율 / 쌍 수): ' + ', '.join(f'{k}점→{a:.0%}/{b:.0%}/{n}' for k, (a, b, n) in sorted(ds['fidelity_by_label_of_source'].items())), '']
    for pname in SETS:
        L.append(f'== 응답 선명도: {pname} (잡음 0.2, 2칸, UCB) -- 풀의 핵심 발견 / 승격 중 0점 / 승격 건수(연구실당) / 무관 노출')
        L.append(f"  {'V(연구실당)':>12} " + ' '.join(f'{m:>26}' for m in ('N0', 'N1', 'N1g', 'N2')))
        for V in VS:
            L.append(f"  {V:>5}({V // 20:>3}번) " + ' '.join(f"{f(g(m, pname, V)['found_two']):>6} /{f(g(m, pname, V)['prom_zero']):>5} /{g(m, pname, V)['prom_per_lab']:>5.2f} /{f(g(m, pname, V)['bad_imp']):>4}" for m in ('N0', 'N1', 'N1g', 'N2')))
        L.append('')
    L.append('판정')
    for k, v in crit.items():
        L.append(f"  {k}: {'통과' if v['ok'] else '실패'}  { {a: b for a, b in v.items() if a != 'ok'} }")
    (HERE / 'results/propagate_table.txt').write_text('\n'.join(L), encoding='utf-8')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
