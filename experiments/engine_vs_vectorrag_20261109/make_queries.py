"""One blind Sonnet call: student-style search queries from the department list and type quotas only."""
import json, subprocess
from pathlib import Path
OUT = Path(__file__).resolve().parent
DEPTS = ['컴퓨터공학과','인공지능대학원','전자전기공학과','반도체공학과','기계공학과','산업경영공학과','화학공학과','화학과','생명과학과','물리학과','수학과','신소재공학과','의공학과','환경공학부','친환경소재대학원 배터리공학과','첨단원자력공학부']
SCHEMA = {'type':'object','additionalProperties':False,'required':['queries'],'properties':{'queries':{'type':'array','minItems':20,'maxItems':20,'items':{'type':'object','additionalProperties':False,'required':['type','text'],'properties':{'type':{'type':'string'},'text':{'type':'string'}}}}}}
PROMPT = f"""POSTECH 학부생이 연구참여할 연구실을 찾으려고 서비스 검색창에 입력할 만한 문장 20개를 만드세요.
학과 목록: {', '.join(DEPTS)}. 여러 학과가 고르게 나오게 하되 어떤 연구실이나 교수의 이름도 쓰지 마세요.
유형별 개수: keyword(짧은 키워드 2~4단어) 5, sentence(자연스러운 한 문장) 5, dislike(좋아하는 것과 피하고 싶은 것을 함께 말함) 3, course(재밌었던 수업 이름으로 말함) 3, long(관심·방식·기간 등을 두세 문장으로) 2, english(영어) 2.
실제 학부생 말투로, 전문 용어를 모르는 경우도 섞어 주세요. type에는 유형 이름을 쓰세요."""
proc = subprocess.run(['claude','-p','--model','sonnet','--effort','medium','--tools','','--no-session-persistence','--output-format','json','--json-schema',json.dumps(SCHEMA,separators=(',',':'))],input=PROMPT,text=True,capture_output=True,cwd='/tmp',timeout=300)
out = json.loads(proc.stdout)
(OUT/'queries_blind.json').write_text(json.dumps(out['structured_output']['queries'],ensure_ascii=False,indent=1))
for q in out['structured_output']['queries']: print(q['type'],'|',q['text'])
