"""실험 1: 피드백과 무관한 자격 관문 기준 비교 + 5-겹 교차검증(연구실 단위). 결과: results/gate_*.{json,txt}"""
import json, random, statistics
from common import load, HERE

cands = load()
labs = sorted(cands)


def rules():
    out = {}
    for t in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5):
        out[f'rr>={t}'] = lambda r, t=t: r['rr'] >= t
        out[f'shared>=1 & rr>={t}'] = lambda r, t=t: r['shared'] >= 1 and r['rr'] >= t
        out[f'shared>=1 | rr>={t}'] = lambda r, t=t: r['shared'] >= 1 or r['rr'] >= t
    out['shared>=1'] = lambda r: r['shared'] >= 1
    for k in (3, 5, 8, 10, 15):
        out[f'rank<={k}'] = lambda r, k=k: r['rank'] <= k
    return out


def evaluate(rule, subset):
    lens, zero, kept = [], 0, 0
    rel_all = rel_kept = top_all = top_kept = 0
    for lab in subset:
        passed = [r for r in cands[lab] if rule(r)]
        lens.append(len(passed))
        kept += len(passed); zero += sum(r['label'] == 0 for r in passed)
        rel_all += sum(r['label'] >= 1 for r in cands[lab]); rel_kept += sum(r['label'] >= 1 for r in passed)
        top_all += sum(r['label'] == 2 for r in cands[lab]); top_kept += sum(r['label'] == 2 for r in passed)
    return {'zero_rate': zero / kept if kept else 0.0, 'recall_rel': rel_kept / rel_all, 'recall_top': top_kept / top_all,
            'len_median': statistics.median(lens), 'labs_lt3': sum(l < 3 for l in lens), 'labs_0': sum(l == 0 for l in lens),
            'cover3': sum(l >= 3 for l in lens) / len(lens), 'mean_len': statistics.mean(lens)}


def pick(R, subset):
    """사전 등록된 선택 규칙: 0점 비율<=25% & cover3>=90% 중 관련 회수율 최대, 없으면 cover3>=90% 중 0점 비율 최소."""
    ev = {n: evaluate(f, subset) for n, f in R.items()}
    ok = [n for n, e in ev.items() if e['zero_rate'] <= 0.25 and e['cover3'] >= 0.9]
    if ok:
        return max(ok, key=lambda n: ev[n]['recall_rel']), True
    ok = [n for n, e in ev.items() if e['cover3'] >= 0.9] or list(ev)
    return min(ok, key=lambda n: ev[n]['zero_rate']), False


R = rules()
base = evaluate(lambda r: True, labs)
full = {n: evaluate(f, labs) for n, f in R.items()}
rnd = random.Random(0); order = labs[:]; rnd.shuffle(order)
folds = [order[i::5] for i in range(5)]
cv = []
for i, test in enumerate(folds):
    train = [l for l in labs if l not in test]
    name, met = pick(R, train)
    cv.append({'fold': i, 'rule': name, 'criteria_met_on_train': met, 'train': evaluate(R[name], train), 'test': evaluate(R[name], test)})
final, met = pick(R, labs)
lines = [f"기준선(관문 없음, 상위30 전체): 0점 {base['zero_rate']:.0%} 관련회수 {base['recall_rel']:.0%} 길이 {base['mean_len']:.0f}", '',
         f"{'규칙':26} {'0점비율':>7} {'관련회수':>8} {'핵심회수':>8} {'길이중앙':>8} {'<3개':>5} {'0개':>4}"]
for n, e in sorted(full.items(), key=lambda kv: kv[1]['zero_rate']):
    lines.append(f"{n:26} {e['zero_rate']:7.0%} {e['recall_rel']:8.0%} {e['recall_top']:8.0%} {e['len_median']:8.1f} {e['labs_lt3']:5d} {e['labs_0']:4d}")
lines += ['', '5-겹 교차검증(검증 연구실 4곳씩):']
for c in cv:
    t = c['test']; lines.append(f"  fold{c['fold']} 선택={c['rule']:24} 기준충족={c['criteria_met_on_train']!s:5} | 검증 0점 {t['zero_rate']:.0%} 관련회수 {t['recall_rel']:.0%} 길이중앙 {t['len_median']:.1f} <3개 {t['labs_lt3']}")
avg = lambda k: statistics.mean(c['test'][k] for c in cv)
lines += [f"  검증 평균: 0점 {avg('zero_rate'):.0%}, 관련회수 {avg('recall_rel'):.0%}, 핵심회수 {avg('recall_top'):.0%}, 길이 {avg('mean_len'):.1f}",
          '', f"전체 20곳으로 고른 최종 관문: {final} (기준 충족: {met}) -> {full[final]}"]
(HERE / 'results').mkdir(exist_ok=True)
(HERE / 'results/gate_table.txt').write_text('\n'.join(lines), encoding='utf-8')
json.dump({'final': final, 'criteria_met': met, 'final_metrics': full[final], 'baseline': base, 'cv': cv, 'all_rules': full},
          open(HERE / 'results/gate_result.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n'.join(lines))
