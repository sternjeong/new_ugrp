import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
source = '''import glob,json,re,time,subprocess,sys,importlib.util
if importlib.util.find_spec('sentence_transformers') is None:
 subprocess.check_call([sys.executable,'-m','pip','install','-q','sentence-transformers'])
import numpy as np,torch
from sentence_transformers import SentenceTransformer
assert torch.cuda.is_available()
packet=json.load(open(glob.glob('/kaggle/input/**/packet.json',recursive=True)[0]))
docs=[]; index={}
def add(s):
 if s not in index:
  index[s]=len(docs); docs.append(s)
 return index[s]
labs={k:[add(x) for x in v['core'] if x.strip()] for k,v in packet['labs'].items()}
baseline={}; snippets={}; snippets_text={}
for k,v in packet['courses'].items():
 baseline[k]=[add(x) for x in v['core'] if x.strip()]
 parts=[]
 for text in v['core']:
  title,sep,body=text.partition(' | ')
  if not sep: continue
  body=re.sub(r'^(?:설명|진도):\\s*','',body)
  for item in re.split(r'(?<=[.!?;])\\s+|\\s+(?=\\d+[.)]\\s*)|\\s+[•·]\\s*',body):
   item=item.strip()
   if len(item)>=25:
    for i in range(0,len(item),360):
     piece=item[i:i+360].strip()
     if len(piece)>=25: parts.append(title+' | '+piece)
 parts=list(dict.fromkeys(parts))[:12] or [x for x in v['core'] if x.strip()]
 snippets_text[k]=parts; snippets[k]=[add(x) for x in parts]
t=time.time()
model=SentenceTransformer('BAAI/bge-m3',revision='5617a9f61b028005a4858fdac845db406aefb181',device='cuda').half()
model.max_seq_length=256
load=time.time()-t;t=time.time()
vec=np.asarray(model.encode(docs,batch_size=32,normalize_embeddings=True,show_progress_bar=False),dtype=np.float32)
enc=time.time()-t; result=[]
for pair in packet['pairs']:
 li=labs[pair['lab_id']]; ci=baseline[pair['course_id']]; si=snippets[pair['course_id']]
 if not li or not ci or not si: continue
 a=vec[li]@vec[ci].T; b=vec[li]@vec[si].T
 bi,bj=np.unravel_index(np.argmax(b),b.shape)
 result.append({'pair_id':pair['pair_id'],'baseline':float(a.max()),'snippet':float(b[bi,bj]),'lab_evidence':docs[li[bi]],'course_evidence':docs[si[bj]],'snippet_count':len(si)})
json.dump({'gpu':torch.cuda.get_device_name(0),'model':'BAAI/bge-m3','revision':'5617a9f61b028005a4858fdac845db406aefb181','max_seq_length':256,'documents':len(docs),'load_s':load,'encode_s':enc,'rows':result},open('/kaggle/working/scores.json','w'),ensure_ascii=False)
print('GPU',torch.cuda.get_device_name(0),'pairs',len(result),'documents',len(docs))
'''
nb={'cells':[{'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':source.splitlines(True)}], 'metadata':{'accelerator':'GPU','kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'gpuhub':{'inputs':['experiments/final_graph/results/embedding_field_ablation_v1/packet.json']}},'nbformat':4,'nbformat_minor':5}
(out/'gpu.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2))
