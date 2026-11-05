"""feedback_gate 실험 공통: 후보(R2 상위 30) + 라벨 + 관문용 특징을 읽는다."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load():
    labels = {(l, c): v for l, c, v in json.load(open(HERE / 'labels_all.json', encoding='utf-8'))}
    R2 = json.load(open(ROOT / 'experiments/bge_m3/V4/rankings_v4.json', encoding='utf-8'))['R2']
    lab_concepts = {}
    for line in open(ROOT / 'data/lab_profiles.jsonl', encoding='utf-8'):
        p = json.loads(line)
        lab_concepts[p['lab_id']] = {t['concept'] for t in p.get('topics', []) if t.get('weight') == 'primary'}
    course_concepts = {}
    for line in open(ROOT / 'data/course_profiles.jsonl', encoding='utf-8'):
        p = json.loads(line)
        course_concepts[p['record_id']] = {c['concept'] for c in p.get('concepts', [])}
    cands = {}
    for lab in sorted({l for l, _ in labels}):
        rows = []
        for i, c in enumerate(R2[lab]['top30']):
            cid = c['record_id']
            rows.append({'cid': cid, 'rank': i + 1, 'rr': c['rr_score'], 'score': c['score'],
                         'shared': len(lab_concepts.get(lab, set()) & course_concepts.get(cid, set())),
                         'label': labels[(lab, cid)]})
        cands[lab] = rows
    return cands


def ndcg(labels_in_order, ideal_pool, k):
    """labels_in_order: 보인 순서의 라벨. ideal_pool: 이상적 순서를 만들 전체 후보 라벨."""
    import math
    dcg = sum(r / math.log2(i + 2) for i, r in enumerate(labels_in_order[:k]))
    ideal = sorted(ideal_pool, reverse=True)[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 1.0
