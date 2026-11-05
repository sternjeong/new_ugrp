"""1단계(로컬): 개발·시험 질의의 L0~L2를 계산하고, 임베딩이 필요한 구절 목록을 만든다. 시험 질의의 계획은 출력하지 않는다."""
import sys, json
sys.path.insert(0, '.'); sys.path.insert(0, 'experiments/query_understanding')
from curri.profile_catalog import ProfileCatalog
import pipeline
D = 'experiments/query_understanding/'
cat = ProfileCatalog('data')
dev = json.load(open(D + 'queries.json', encoding='utf-8'))
test = json.load(open(D + 'queries_test.json', encoding='utf-8'))
plans, phrases = {}, set()
for q in dev + test:
    p = pipeline.plan(q['text'], cat)
    plans[q['id']] = p
    phrases.add(p['norm']); phrases.update(p['likes']); phrases.update(p['dislikes'])
phrases = sorted(x for x in phrases if x.strip())
json.dump(plans, open(D + 'plans_v2.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(phrases, open(D + 'phrases_v2.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('질의', len(plans), '고유 구절', len(phrases))
