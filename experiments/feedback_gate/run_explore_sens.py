"""실험 3 민감도(사후 분석, 사전 등록 아님): 응답이 덜 선명할 때·연구실당 응답이 적을 때 탐색 칸이 얼마나 버티는가."""
import json
import run_explore as X
from common import HERE

SETS = {'선명(0.9/0.5/0.1, 사전등록 가정)': {2: 0.9, 1: 0.5, 0: 0.1}, '보통(0.75/0.5/0.25)': {2: 0.75, 1: 0.5, 0: 0.25}, '흐림(0.65/0.5/0.35)': {2: 0.65, 1: 0.5, 0: 0.35}}
out, L = {}, []
fmt = lambda x: '-' if x is None else f'{x:.0%}'
for name, p in SETS.items():
    X.P_YES.clear(); X.P_YES.update(p)
    r = X.aggregate('E', 2, 'ucb', 0.2, 0.0); out[name] = r
    L.append(f'응답 확률 {name} -- S=2, UCB, 잡음 0.2')
    L.append(f"  {'T':>4} {'승격(건/연구실)':>14} {'승격중 0점':>10} {'승격중 >=1':>10} {'풀 핵심 발견':>11} {'무관 노출':>8} {'최종 0점':>8} {'핵심 수(본→최종)':>14}")
    for T in X.CHECK:
        x = r[T]; L.append(f"  {T:>4} {x['promoted_per_lab']:14.2f} {fmt(x['prom_zero_rate']):>10} {fmt(x['prom_rel_rate']):>10} {fmt(x['found_two_in_pool']):>11} {fmt(x['bad_impression_rate']):>8} {fmt(x['final_zero_rate']):>8} {x['core_two_per_lab']:.2f}→{x['final_two_per_lab']:.2f}")
    L.append('')
(HERE / 'results/explore_sensitivity.txt').write_text('\n'.join(L), encoding='utf-8')
json.dump(out, open(HERE / 'results/explore_sensitivity.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n'.join(L))
