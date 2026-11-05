import json
from pathlib import Path

out=Path(__file__).resolve().parent
src='''import json,glob,re,time,importlib.util,subprocess,sys
if importlib.util.find_spec('sentence_transformers') is None:
 subprocess.check_call([sys.executable,'-m','pip','install','-q','sentence-transformers'])
import torch,numpy as np
from sentence_transformers import SentenceTransformer
assert torch.cuda.is_available()
cases=json.load(open(glob.glob('/kaggle/input/**/cases.json',recursive=True)[0]))
sent=lambda t:[s.strip() for s in re.split(r'(?<=[.!?])\\s+|\\n+',t) if len(s.strip())>=30]
docs=[]; ids={}
def add(t):
 if t not in ids:ids[t]=len(docs);docs.append(t)
 return ids[t]
refs=[]
for c in cases:
 ps=sent(c['paper']['abstract'])[:30]
 cs=sent(' '.join(z['description']+'\\n'+z['plan'] for z in c['courses']))[:30]
 if ps and cs:refs.append((c['id'],[add(x) for x in ps],[add(x) for x in cs]))
t=time.time();m=SentenceTransformer('BAAI/bge-m3',revision='5617a9f61b028005a4858fdac845db406aefb181',device='cuda').half();m.max_seq_length=256
e=np.asarray(m.encode(docs,batch_size=32,normalize_embeddings=True,show_progress_bar=False),dtype=np.float32);rows=[]
for cid,p,c in refs:
 s=e[p]@e[c].T;i,j=np.unravel_index(np.argmax(s),s.shape)
 rows.append({'case_id':cid,'similarity':float(s[i,j]),'paper_sentence':docs[p[i]],'course_sentence':docs[c[j]],'paper_candidates':len(p),'course_candidates':len(c)})
json.dump({'gpu':torch.cuda.get_device_name(0),'model':'BAAI/bge-m3','revision':'5617a9f61b028005a4858fdac845db406aefb181','elapsed_s':time.time()-t,'rows':rows},open('/kaggle/working/gpu_evidence.json','w'),ensure_ascii=False,indent=2)
print('GPU',torch.cuda.get_device_name(0),'cases',len(rows))
'''
notebook={'cells':[{'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':src.splitlines(True)}],
 'metadata':{'accelerator':'GPU','kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'gpuhub':{'inputs':['experiments/research_extreme_20261105/cases.json']}},'nbformat':4,'nbformat_minor':5}
(out/'gpu.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2))
