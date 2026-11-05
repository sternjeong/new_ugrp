import json
cells = []
def md(s): cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': s.strip('\n').splitlines(True)})
def code(s): cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': s.strip('\n').splitlines(True)})

md("""
# 관심 질의 해석 + 연구실 검색 실험 v1

홈에서 입력한 관심 문장을 연구실 검색으로 연결하는 방법을 비교한다. 문제: "나는 로봇은 싫은데 컴퓨터 아키텍처는 좋아요"를 통째로 검색하면 로봇 연구실이 나오고, "컴퓨터 아키텍처"가 "컴퓨터"로 쪼개지면 엉뚱한 연구실이 나온다.

| 방법 | 질의 처리 | 검색 |
|---|---|---|
| (로컬) A 현재 앱 | 개념 사전 키워드 | 규칙 점수 |
| B | 없음 (문장 전체) | bge-m3 임베딩 최대 유사도 |
| C | 규칙으로 좋아함/싫어함 분리, 구절 유지 | 구절별 임베딩, 좋아함 평균 z − λ·싫어함 최대 z |
| D | Qwen2.5-7B가 JSON으로 분리 (구절 그대로) | C와 같음 |

연구실 문서: 0 = 프로필(요약+주제 라벨+원문 인용), 1 = 0 + 앱 교수의 대표 논문(제목+초록 앞 500자).

### 입력 (gpuhub가 자동 연결)
`data/lab_profiles.jsonl`, `experiments/query_understanding/queries.json`, `papers_app.jsonl`, `rule_interpreter.py`
""")
code("""
import torch
print('GPU 사용 가능:', torch.cuda.is_available())
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
""")
code("!pip install -q sentence-transformers transformers accelerate bitsandbytes")
code("""
import os, glob, shutil
need = ['lab_profiles.jsonl', 'queries.json', 'papers_app.jsonl', 'rule_interpreter.py']
ON_KAGGLE = os.path.exists('/kaggle/input')
if ON_KAGGLE:
    for f in need:
        hits = glob.glob(f'/kaggle/input/**/{f}', recursive=True)
        if not os.path.exists(f) and hits:
            shutil.copy(hits[0], f)
missing = [f for f in need if not os.path.exists(f)]
if missing and not ON_KAGGLE:
    from google.colab import files
    files.upload()
missing = [f for f in need if not os.path.exists(f)]
assert not missing, f'아직 없는 파일: {missing}'
print('데이터 준비 완료')
""")
code("""
import json, re, time
import numpy as np
from collections import defaultdict

def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]

labs = [p for p in load_jsonl('lab_profiles.jsonl') if p.get('status') != 'insufficient']
lab_ids = [p['lab_id'] for p in labs]
queries = json.load(open('queries.json', encoding='utf-8'))
papers = defaultdict(list)
for r in load_jsonl('papers_app.jsonl'):
    papers[r['lab_id']].append(r)

def profile_docs(p):
    docs = [p['summary_ko']] if p.get('summary_ko') else []
    for t in p['topics']:
        docs.append(f"{t['label_ko']}: {t['quote'][:400]}")
    return docs
def paper_docs(lid):
    return [f"{r['title']}. {r['abstract'][:500]}".strip() for r in papers.get(lid, [])]

DOCS = {'0': {lid: profile_docs(p) for lid, p in zip(lab_ids, labs)},
        '1': {lid: profile_docs(p) + paper_docs(lid) for lid, p in zip(lab_ids, labs)}}
print('연구실', len(labs), '질의', len(queries), '논문 있는 연구실', sum(1 for l in lab_ids if papers.get(l)))
print('문서 수 (프로필 / +논문):', sum(len(v) for v in DOCS['0'].values()), sum(len(v) for v in DOCS['1'].values()))
""")
code("""
from sentence_transformers import SentenceTransformer
device = 'cuda' if torch.cuda.is_available() else 'cpu'
emb = SentenceTransformer('BAAI/bge-m3', device=device)
if device == 'cuda':
    emb.half()
def encode(texts, bs=32):
    return np.asarray(emb.encode(texts, batch_size=bs, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)

DOCMAT = {}
for v, per_lab in DOCS.items():
    texts, starts = [], []
    for lid in lab_ids:
        starts.append(len(texts)); texts.extend(per_lab[lid])
    DOCMAT[v] = (encode(texts), np.array(starts))
    print('변형', v, '문서 임베딩', DOCMAT[v][0].shape)

def lab_sims(phrases, v):
    \"\"\"구절 × 연구실: 연구실 문서 중 최대 코사인 유사도\"\"\"
    E = encode(phrases)
    D, starts = DOCMAT[v]
    return np.maximum.reduceat(E @ D.T, starts, axis=1)
""")
md("## 질의 해석: C 규칙 / D Qwen2.5-7B")
code("""
from rule_interpreter import interpret
interp_rule = {q['id']: interpret(q['text']) for q in queries}
for q in queries[:5]:
    print(q['text'], '->', interp_rule[q['id']])
""")
code("""
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
LLM_ID = 'Qwen/Qwen2.5-7B-Instruct'
t0 = time.time()
tok = AutoTokenizer.from_pretrained(LLM_ID, trust_remote_code=True)
tok.padding_side = 'left'
llm = AutoModelForCausalLM.from_pretrained(
    LLM_ID, device_map={'': 0} if torch.cuda.is_available() else 'cpu', trust_remote_code=True,
    quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_quant_type='nf4'))
print(f'LLM 로드 {time.time()-t0:.1f}s')

SYSTEM = (
    "너는 대학생이 쓴 관심 문장에서 '좋아하는 주제'와 '싫어하거나 빼고 싶은 주제'를 구분해 JSON으로만 답한다.\\n"
    "규칙:\\n"
    "- likes: 학생이 관심 있다고 한 주제 구절 목록. dislikes: 싫다, 별로, 관심 없다, 질렸다, ~보다는, ~말고, 빼고 등으로 밀어낸 주제 구절 목록.\\n"
    "- 구절은 학생이 쓴 말을 그대로 쓰되 조사와 서술어는 뗀다. '컴퓨터 아키텍처'처럼 둘 이상의 단어로 된 전문 용어는 절대 쪼개지 않는다.\\n"
    "- 싫다고 한 주제를 likes에 넣지 않는다. 학생이 말하지 않은 주제를 새로 만들지 않는다.\\n"
    "- 한쪽이 없으면 빈 목록 []을 쓴다. 출력은 {\\"likes\\": [...], \\"dislikes\\": [...]} 한 줄뿐이다.")
SHOTS = [
    ("수학은 싫지만 암호가 좋아요", {"likes": ["암호"], "dislikes": ["수학"]}),
    ("음악 생성 AI와 로봇 팔 제어가 궁금해요", {"likes": ["음악 생성 AI", "로봇 팔 제어"], "dislikes": []}),
    ("웹 개발보다는 운영체제 커널을 하고 싶어요", {"likes": ["운영체제 커널"], "dislikes": ["웹 개발"]}),
    ("게임은 이미 질렸고 자율주행 자동차에 끌려요", {"likes": ["자율주행 자동차"], "dislikes": ["게임"]}),
]
def messages_for(text):
    m = [{'role': 'system', 'content': SYSTEM}]
    for u, a in SHOTS:
        m += [{'role': 'user', 'content': u}, {'role': 'assistant', 'content': json.dumps(a, ensure_ascii=False)}]
    return m + [{'role': 'user', 'content': text}]

def generate(messages_list, max_new=120, bs=8):
    outs = []
    for i in range(0, len(messages_list), bs):
        texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in messages_list[i:i+bs]]
        enc_in = tok(texts, return_tensors='pt', padding=True).to(llm.device)
        with torch.no_grad():
            out = llm.generate(**enc_in, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
        for ids in out[:, enc_in['input_ids'].shape[1]:]:
            outs.append(tok.decode(ids, skip_special_tokens=True).strip())
    return outs

t0 = time.time()
raw = generate([messages_for(q['text']) for q in queries])
llm_seconds = time.time() - t0
interp_llm, parse_fail = {}, []
for q, r in zip(queries, raw):
    try:
        j = json.loads(re.search(r'\\{.*\\}', r, re.S).group(0))
        interp_llm[q['id']] = {'likes': [str(x) for x in j.get('likes', [])], 'dislikes': [str(x) for x in j.get('dislikes', [])]}
    except Exception:
        parse_fail.append(q['id'])
        interp_llm[q['id']] = {'likes': [], 'dislikes': []}
print(f'LLM 해석 {llm_seconds:.1f}s (질의당 {llm_seconds/len(queries):.2f}s), JSON 실패 {len(parse_fail)}건', parse_fail)
for q in queries[:6]:
    print(q['text'], '->', interp_llm[q['id']])
""")
md("## 점수 계산과 순위 저장")
code("""
LAMS = [0, 0.5, 1, 2]
def zs(x):
    return (x - x.mean(axis=-1, keepdims=True)) / (x.std(axis=-1, keepdims=True) + 1e-9)

ranks = defaultdict(dict)
def order(score):
    return [lab_ids[i] for i in np.argsort(-score)]

for v in ['0', '1']:
    for q in queries:
        ranks[f'B{v}'][q['id']] = order(lab_sims([q['text']], v)[0])
    for name, interp in [('C', interp_rule), ('D', interp_llm)]:
        for lam in LAMS:
            for q in queries:
                it = interp[q['id']]
                likes = it['likes'] or [q['text']]          # 해석 실패 시 문장 전체로 후퇴
                zl = zs(lab_sims(likes, v)).mean(axis=0)
                pen = np.zeros(len(lab_ids))
                if it['dislikes'] and lam:
                    pen = np.maximum(0, zs(lab_sims(it['dislikes'], v))).max(axis=0)
                ranks[f'{name}{v}_l{lam}'][q['id']] = order(zl - lam * pen)
print(sorted(ranks))
""")
code("""
# CPU에서 질의 하나를 임베딩하는 데 걸리는 시간 (서버에 임베딩을 올릴 수 있는지 판단)
emb.float(); emb.to('cpu')
phrases = [q['text'] for q in queries]
t0 = time.time()
for p in phrases:
    emb.encode([p], normalize_embeddings=True, show_progress_bar=False)
cpu_ms = (time.time() - t0) / len(phrases) * 1000
print(f'CPU 질의 임베딩 평균 {cpu_ms:.0f} ms (문서 임베딩은 미리 계산해 두는 것을 가정)')
""")
code("""
import zipfile
json.dump(ranks, open('ranks_v1.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({'rule': interp_rule, 'llm': interp_llm, 'llm_raw': dict(zip([q['id'] for q in queries], raw)), 'llm_parse_fail': parse_fail}, open('interp_v1.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({'EMB': 'BAAI/bge-m3', 'LLM_ID': LLM_ID, 'LAMS': LAMS, 'cpu_query_ms': cpu_ms, 'llm_seconds': llm_seconds, 'n_labs': len(lab_ids), 'n_queries': len(queries),
           'docs': {v: sum(len(x) for x in d.values()) for v, d in DOCS.items()}}, open('settings_v1.json', 'w'), indent=1)
with zipfile.ZipFile('query_results_v1.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in ['ranks_v1.json', 'interp_v1.json', 'settings_v1.json']:
        z.write(f)
print('저장 완료')
""")
nb = {'cells': cells, 'metadata': {'accelerator': 'GPU', 'colab': {'provenance': [], 'gpuType': 'T4'}, 'kernelspec': {'display_name': 'Python 3', 'name': 'python3'}, 'language_info': {'name': 'python'},
      'gpuhub': {'inputs': ['data/lab_profiles.jsonl', 'experiments/query_understanding/queries.json', 'experiments/query_understanding/papers_app.jsonl', 'experiments/query_understanding/rule_interpreter.py']}},
      'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open('query_understanding_v1.ipynb', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('ok', len(cells))
