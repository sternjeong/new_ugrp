"""Generate preregistered admin-chunk shuffle sensitivity on Kaggle GPU."""

import json
from pathlib import Path

from make_embedding_field_ablation_kaggle import CODE

HERE = Path(__file__).resolve().parent
OUT = HERE / "shuffled_admin_kaggle.ipynb"

EXTRA = r'''
def shuffled_admin_map(group, index, tag):
    filled = [x['id'] for x in group if index[x['id']]['admin']]
    assert all(len(index[x]['admin']) == 1 for x in filled)
    ordered = sorted(filled, key=lambda x: hashlib.sha256((tag+'|'+x).encode()).hexdigest())
    rotated = ordered[1:] + ordered[:1]
    mapping = {dst:index[src]['admin'] for dst,src in zip(ordered,rotated)}
    assert len(mapping) == len(filled)
    return mapping

lab_shuffle = shuffled_admin_map(labs, lab_ix, 'lab_shuffle_20261016')
course_shuffle = shuffled_admin_map(courses, course_ix, 'course_shuffle_20261016')
course_ids = [x['id'] for x in courses]
def ids(index, entity, mapping):
    return index[entity]['core'] + mapping.get(entity,[])
rankings = []
for lab in labs:
    lab_id = lab['id']
    li = ids(lab_ix,lab_id,lab_shuffle)
    best = sim[li].max(axis=0)
    scores = []
    for course_id in course_ids:
        ci = ids(course_ix,course_id,course_shuffle)
        scores.append((float(best[ci].max()),course_id))
    scores.sort(key=lambda x:(-x[0],x[1]))
    rankings.append({'lab_id':lab_id,'shuffled_admin':[{'course_id':cid,'score':round(score,6)} for score,cid in scores[:30]]})
path = OUTPUT/'shuffled_admin_rankings.json'
path.write_text(json.dumps(rankings,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
manifest = {'status':'structural_sensitivity_unjudged','rankings_sha256':sha(path),
            'profiles_sha256':sha(profiles_path),'frame_sha256':sha(frame_path),
            'device':str(next(model.parameters()).device),'cuda_name':torch.cuda.get_device_name(0),
            'model':'BAAI/bge-m3','model_revision':revision,'max_seq_length':model.max_seq_length,
            'shuffle':'nonempty admin chunks within entity kind; sha256 order, cyclic rotation',
            'lab_nonempty':len(lab_shuffle),'course_nonempty':len(course_shuffle)}
(OUTPUT/'shuffled_admin_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False))
'''


def main():
    code = CODE.split("variants = {")[0] + EXTRA
    compile(code, str(OUT), "exec")
    nb = {"cells": [
        {"cell_type":"markdown","metadata":{},"source":["# Shuffled admin structural sensitivity\n","CUDA only; no quality labels loaded.\n"]},
        {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":["%pip -q install sentence-transformers==6.1.0\n"]},
        {"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],"source":[line+'\n' for line in code.strip().splitlines()]}
    ],"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
                   "language_info":{"name":"python"},"gpuhub":{"inputs":[
                       "experiments/final_graph/results/embedding_field_ablation_v1/profiles.json",
                       "experiments/final_graph/results/embedding_field_ablation_v1/profiles_manifest.json",
                       "experiments/final_graph/results/embedding_field_ablation_v1/frame.json"]}},
        "nbformat":4,"nbformat_minor":5}
    OUT.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
