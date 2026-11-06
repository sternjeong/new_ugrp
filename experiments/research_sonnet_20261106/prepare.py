import hashlib,json
from pathlib import Path
from curri.curated_catalog import CuratedCatalog

root=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
prior=root/'experiments/research_extreme_20261105'
old=json.loads((prior/'cases.json').read_text());clusters=list(dict.fromkeys(c['cluster'] for c in old))
selected=[c for c in old if c['condition']=='course1' or
          (c['cluster'] in clusters[:4] and c['condition'] in ('course2','interest','none'))]
assert len(selected)==24 and len({c['cluster'] for c in selected})==12
catalog=CuratedCatalog(root/'data/sunwoo')
for c in selected:
 c['lab_sources']=[{'label':t['label_ko'],'text':t['quote']} for t in catalog.profiles[c['lab_id']]['topics'][:3]]
baseline={x['case_id']:x['text'] for x in json.loads((prior/'baseline.json').read_text())}
assert all(c['id'] in baseline for c in selected)
(out/'cases.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
(out/'baseline.json').write_text(json.dumps([{'case_id':c['id'],'text':baseline[c['id']]} for c in selected],ensure_ascii=False,indent=2))
files=[prior/'cases.json',root/'data/sunwoo/app_profiles.jsonl',root/'data/sunwoo/courses.jsonl',root/'data/sunwoo/papers.jsonl',out/'cases.json']
(out/'manifest.json').write_text(json.dumps({str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
print('cases',len(selected),'labs',len(clusters),'selected course',sum(bool(c['courses']) for c in selected))
