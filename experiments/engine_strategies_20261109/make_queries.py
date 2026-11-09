"""Blind Sonnet call: 50 realistic and odd inputs from category quotas only. The two examples from the request are fixed."""
import json, subprocess
from pathlib import Path
OUT = Path(__file__).resolve().parent
QUOTAS = {'keyword': (6, '짧은 키워드 2~4단어'), 'sentence': (10, '자연스러운 한 문장으로 연구 관심을 말함'),
          'like_dislike': (6, '좋아하는 것과 피하고 싶은 것을 함께 말함'), 'dislike_only': (3, '싫어하는 것만 말함, 예: 수학이 너무 싫어요'),
          'course': (5, '재밌었거나 인상 깊은 수업 이름으로 말함'), 'long': (4, '관심·방식·기간 등을 두세 문장으로'),
          'english': (3, '영어 또는 한영 혼합'), 'everyday': (5, '연구실과 먼 일상적 궁금증, 예: 왜 커피를 마시면 잠이 안 올까'),
          'off_topic': (3, '연구와 무관하거나 장난, 예: 오늘 점심 뭐 먹지, ㅋㅋㅋ'), 'procedure': (2, '학교 절차 질문, 예: 대학원 지원 방법'),
          'too_broad': (1, '너무 넓은 한두 단어')}
SCHEMA = {'type':'object','additionalProperties':False,'required':['queries'],'properties':{'queries':{'type':'array','minItems':48,'maxItems':48,'items':{'type':'object','additionalProperties':False,'required':['type','text'],'properties':{'type':{'type':'string','enum':list(QUOTAS)},'text':{'type':'string'}}}}}}
PROMPT = "POSTECH 학부생이 '관심을 입력하면 연구실을 찾아 주는' 서비스 검색창에 실제로 입력할 만한 문장을 만드세요. 어떤 연구실·교수 이름도 쓰지 말고, 컴퓨터·전자·기계·화학·생명·물리·수학·신소재·산업공학·환경·에너지 분야가 고르게 나오게 하세요. 전문 용어를 모르는 학부생의 말투도 섞으세요.\n유형별 개수와 설명:\n" + '\n'.join(f'- {k}: {n}개, {d}' for k,(n,d) in QUOTAS.items())
proc = subprocess.run(['claude','-p','--model','sonnet','--effort','medium','--tools','','--no-session-persistence','--output-format','json','--json-schema',json.dumps(SCHEMA,separators=(',',':'))],input=PROMPT,text=True,capture_output=True,cwd='/tmp',timeout=300)
qs = json.loads(proc.stdout)['structured_output']['queries']
qs += [{'type':'dislike_only','text':'나는 로봇이 싫어요'},{'type':'everyday','text':'나는 잠이 인체에 어떤 영향을 주는지 알고 싶어요'}]
out = [{'id':f'q{i+1:02d}',**q} for i,q in enumerate(qs)]
(OUT/'queries.json').write_text(json.dumps(out,ensure_ascii=False,indent=1))
import collections; print(collections.Counter(q['type'] for q in out))
for q in out: print(q['id'],q['type'],'|',q['text'])
