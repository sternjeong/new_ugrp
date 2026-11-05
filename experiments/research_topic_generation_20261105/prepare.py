import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
papers={r['id']:r['papers'] for r in map(json.loads,open(root/'data/sunwoo/papers.jsonl'))}
courses={r['code']:r for r in map(json.loads,open(root/'data/sunwoo/courses.jsonl'))}
labs={r['id']:r for r in map(json.loads,open(root/'data/sunwoo/labs.jsonl'))}
specs=[
 ('sensor','0e0e57ecc9ee50a999b2c99ed31dcf93','A Wearable Stethoscope',
  '호흡음에서 천식과 관련된 신호를 분석하고 싶어요','착용형 의료 센서의 신호 잡음을 줄이고 싶어요','EECE482','EECE331'),
 ('robot','6dda7a495187db5785ed7f2f11e30511','DextER:',
  '로봇 손이 물체를 안정적으로 잡는 방법이 궁금해요','언어 지시를 이해하는 로봇의 판단이 궁금해요','EECE320','CSED515'),
 ('chem','bd6528b8c777c23bf9cc24efa89579b1','Electrosynthesis of',
  '유기 분자에 새로운 결합을 만드는 반응이 궁금해요','전기화학 반응에서 반응 조건의 역할이 궁금해요','CHEM221','CHEB469E')]
cases=[]
for group,lid,prefix,interest,alt,code,other in specs:
 p=next(p for p in papers[lid] if p['title'].startswith(prefix))
 def course(code):
  c=courses[code];return {'id':code,'title':c['title'],'description':(c.get('description') or '')[:900], 'plan':(c.get('lecture_plan') or '')[:900]}
 for typ,q,ids in [('base',interest,[code]),('interest',alt,[code]),('course',interest,[other]),('none',interest,[])]:
  cases.append({'id':group+'_'+typ,'group':group,'condition':typ,'interest':q,'professor':labs[lid]['professor']['name_ko'],
                'lab_id':lid,'paper':{'id':p['openalex_id'],'title':p['title'],'abstract':(p.get('abstract') or '')[:1600]},
                'courses':[course(c) for c in ids]})
(out/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
source='''import json,glob,time,importlib.util,subprocess,sys,torch
if importlib.util.find_spec('transformers') is None:
 subprocess.check_call([sys.executable,'-m','pip','install','-q','transformers','accelerate'])
from transformers import AutoModelForCausalLM,AutoTokenizer
assert torch.cuda.is_available()
cases=json.load(open(glob.glob('/kaggle/input/**/cases.json',recursive=True)[0]))
model_id='Qwen/Qwen2.5-3B-Instruct'
t=time.time();tokenizer=AutoTokenizer.from_pretrained(model_id);model=AutoModelForCausalLM.from_pretrained(model_id,torch_dtype=torch.float16,device_map='auto');load=time.time()-t
rules={
'A':'Suggest one concrete research topic and explain why it fits the student and lab. Answer in Korean.',
'B':'Suggest one feasible research exploration for the student. Distinguish (1) research question, (2) what the paper actually states, (3) a specific course concept and how it might help, and (4) unknowns and a small first step. Cite the exact paper ID and course ID when used. Use only supplied evidence for factual claims; label proposed uses as suggestions. If no course is supplied do not infer lack of skill or invent a course. Never claim the proposed topic is an existing lab project or that access to data/equipment is available. Answer in Korean.'}
outputs=[];t=time.time()
for case in cases:
 for method in ['A','B']:
  messages=[{'role':'system','content':'You are an academic research exploration advisor. Avoid inventing facts.'},{'role':'user','content':rules[method]+'\\nInput data:\\n'+json.dumps(case,ensure_ascii=False)}]
  prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
  inputs=tokenizer(prompt,return_tensors='pt').to(model.device)
  with torch.inference_mode(): generated=model.generate(**inputs,max_new_tokens=250,do_sample=False,pad_token_id=tokenizer.eos_token_id)
  text=tokenizer.decode(generated[0,inputs['input_ids'].shape[1]:],skip_special_tokens=True)
  outputs.append({'case_id':case['id'],'method':method,'text':text,'tokens':int(generated.shape[1]-inputs['input_ids'].shape[1])})
  print(case['id'],method,flush=True)
json.dump({'model':model_id,'gpu':torch.cuda.get_device_name(0),'load_s':load,'generation_s':time.time()-t,'outputs':outputs},open('/kaggle/working/generations.json','w'),ensure_ascii=False,indent=2)
'''
nb={'cells':[{'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':source.splitlines(True)}], 'metadata':{'accelerator':'GPU','kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'gpuhub':{'inputs':['experiments/research_topic_generation_20261105/cases.json']}},'nbformat':4,'nbformat_minor':5}
(out/'gpu.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=2))
print(len(cases),'cases')
