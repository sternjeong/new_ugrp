"""Kaggle packet and notebook: Qwen parses each query, then BGE-M3 embeds its search text for chunk retrieval.
Run: python3 experiments/engine_strategies_20261109/qwen/prepare.py <proto_dir> <job_dir>"""
import json, re, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent
proto, job = Path(sys.argv[1]), Path(sys.argv[2])
RULES = re.search(r"RULES = '''(.*?)'''", (PARENT / 'llm_parse.py').read_text(), re.S).group(1)
queries = json.loads((PARENT / 'queries.json').read_text())
chunks = [json.loads(l) for l in open(proto / 'data/rag/pack300-whole/chunks.jsonl')]
json.dump({'rules': RULES, 'queries': queries, 'chunks': [f"{c['header']}\n{c['text']}" for c in chunks], 'kinds': [c['kind'] for c in chunks], 'owners': [c['owner'] for c in chunks]},
          open(job / 'packet.json', 'w'), ensure_ascii=False)
code = r'''
import json, glob, re, time, subprocess, sys, importlib.util
if importlib.util.find_spec('sentence_transformers') is None:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'sentence-transformers'])
import numpy as np, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from sentence_transformers import SentenceTransformer
assert torch.cuda.is_available()
p = json.load(open(glob.glob('/kaggle/input/**/packet.json', recursive=True)[0]))
FORMAT = '\n\n아래 JSON 형식으로만 답하세요. 다른 말은 쓰지 마세요.\n{"intent": "search|only_dislike|off_topic|procedure|too_vague", "likes": ["..."], "dislikes": ["..."], "search_text": "..."}'
NAME = 'Qwen/Qwen2.5-7B-Instruct'
t0 = time.time()
tok = AutoTokenizer.from_pretrained(NAME)
llm = AutoModelForCausalLM.from_pretrained(NAME, torch_dtype=torch.float16, device_map={'': 0})
llm.eval()
load_s = time.time() - t0; print('qwen load', load_s, flush=True)
INTENTS = {'search', 'only_dislike', 'off_topic', 'procedure', 'too_vague'}
def parse(raw):
    m = re.search(r'\{.*\}', raw, re.S)
    d = json.loads(m.group(0))
    if d['intent'] not in INTENTS or not isinstance(d['likes'], list) or not isinstance(d['dislikes'], list) or not isinstance(d['search_text'], str):
        raise ValueError('schema')
    return {'intent': d['intent'], 'likes': [str(x) for x in d['likes']], 'dislikes': [str(x) for x in d['dislikes']], 'search_text': d['search_text']}
out = {}
for q in p['queries']:
    msgs = [{'role': 'system', 'content': 'You output only JSON.'}, {'role': 'user', 'content': p['rules'] + FORMAT + '\n\n입력: ' + q['text']}]
    prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    ids = tok(prompt, return_tensors='pt').input_ids.to('cuda:0')
    t1 = time.time()
    with torch.no_grad():
        gen = llm.generate(ids, max_new_tokens=300, do_sample=False, pad_token_id=tok.eos_token_id)
    secs = time.time() - t1
    raw = tok.decode(gen[0][ids.shape[1]:], skip_special_tokens=True)
    try:
        d = parse(raw); d['failed'] = False
    except Exception:
        d = {'intent': 'search', 'likes': [q['text']], 'dislikes': [], 'search_text': q['text'], 'failed': True}
    out[q['id']] = {**d, 'raw': raw[:600], 'seconds': round(secs, 2), 'new_tokens': int(gen.shape[1] - ids.shape[1])}
json.dump({'model': NAME, 'load_s': round(load_s, 1), 'peak_gpu_mb': int(torch.cuda.max_memory_allocated() / 1e6), 'parses': out}, open('qwen_parse.json', 'w'), ensure_ascii=False)
del llm; torch.cuda.empty_cache()
print('parsed', time.time() - t0, flush=True)
model = SentenceTransformer('BAAI/bge-m3', device='cuda'); model.half()
enc = lambda t, b=32: np.asarray(model.encode(list(t), batch_size=b, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
V = enc(p['chunks'], 16)
lab_kinds = {'profile', 'intro', 'paper'}
owners = sorted({o for o, k in zip(p['owners'], p['kinds']) if k in lab_kinds})
idx = {o: [i for i, (x, k) in enumerate(zip(p['owners'], p['kinds'])) if x == o and k in lab_kinds] for o in owners}
W = np.array([1.0, 0.3, 0.15])
texts = sorted({t for d in out.values() if d['intent'] == 'search' for t in [d['search_text']] + d['dislikes'] if t.strip()})
Q = enc(texts)
sims = {}
for i, text in enumerate(texts):
    s = V @ Q[i]
    row = []
    for o in owners:
        top = np.sort(s[idx[o]])[::-1][:3]
        row.append(round(float((W[:len(top)] * top).sum()), 5))
    sims[text] = row
json.dump({'owners': owners, 'sims': sims}, open('qwen_chunk_sims.json', 'w'), ensure_ascii=False)
print('done', time.time() - t0)
'''
nb = {'cells': [{'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': code.strip().splitlines(True)}],
      'metadata': {'accelerator': 'GPU', 'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'}, 'gpuhub': {'inputs': ['packet.json']}}, 'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open(job / 'gpu_qwen.ipynb', 'w'))
