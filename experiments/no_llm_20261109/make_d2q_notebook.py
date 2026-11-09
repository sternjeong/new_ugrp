import json, sys
code = r'''
import glob, json, re, time
import numpy as np, torch
import torch.nn.functional as F
assert torch.cuda.is_available()
p = json.load(open(glob.glob('/kaggle/input/**/packet.json', recursive=True)[0]))
from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
name = 'Qwen/Qwen2.5-7B-Instruct'
tok = AutoTokenizer.from_pretrained(name, padding_side='left')
m = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float16, device_map='auto').eval()
ask = """다음은 대학 연구실 정보입니다. 이 연구실을 찾을 학부생이 검색창에 쓸 법한 표현을 만드세요.
JSON만 출력하세요: {"keywords": [...], "questions": [...]}
- keywords: 이 연구실의 연구를 가리키는 한국어 연구 용어와 쉬운 일상어 12개.
- questions: 연구 용어를 모르는 학생이 이 연구와 관련해 일상에서 품을 만한 짧은 궁금증 6개 (예: '왜 ~할까요').
정보에 없는 분야를 지어내지 마세요.

연구실 정보: """
out, bad = {}, []
cards = p['cards']
t0 = time.time()
for i in range(0, len(cards), 4):
    batch = cards[i:i + 4]
    prompts = [tok.apply_chat_template([{'role': 'user', 'content': ask + c['text']}], tokenize=False, add_generation_prompt=True) for c in batch]
    enc = tok(prompts, return_tensors='pt', padding=True, truncation=True, max_length=1500).to(m.device)
    with torch.no_grad():
        gen = m.generate(**enc, max_new_tokens=420, do_sample=False)
    for c, row in zip(batch, gen):
        text = tok.decode(row[enc.input_ids.shape[1]:], skip_special_tokens=True)
        try:
            d = json.loads(text[text.index('{'):text.rindex('}') + 1])
            out[c['lab_id']] = {'keywords': [str(x) for x in d['keywords']][:14], 'questions': [str(x) for x in d['questions']][:8]}
        except Exception:
            bad.append(c['lab_id']); out[c['lab_id']] = {'keywords': re.findall(r'"([^"]{2,30})"', text)[:14], 'questions': []}
    print('d2q', i, round(time.time() - t0), flush=True)
    json.dump({'labs': out, 'failed_json': bad, 'seconds': round(time.time() - t0, 1)}, open('d2q.json', 'w'), ensure_ascii=False)
del m
import gc; gc.collect(); torch.cuda.empty_cache()
from huggingface_hub import snapshot_download
snap = snapshot_download('BAAI/bge-m3')
tok = AutoTokenizer.from_pretrained(snap)
m = AutoModel.from_pretrained(snap, torch_dtype=torch.float16).cuda(0).eval()
sl = torch.nn.Linear(1024, 1); sl.load_state_dict(torch.load(snap + '/sparse_linear.pt', map_location='cpu')); sl = sl.half().cuda(0).eval()
skip = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
def enc(texts, bs=32):
    dense, sparse = [], []
    for i in range(0, len(texts), bs):
        e = tok(texts[i:i + bs], padding=True, truncation=True, max_length=512, return_tensors='pt').to('cuda:0')
        with torch.no_grad():
            h = m(**e).last_hidden_state
            d = F.normalize(h[:, 0], dim=-1).float().cpu().numpy()
            w = torch.relu(sl(h)).squeeze(-1)
        for b in range(len(e.input_ids)):
            dense.append(d[b]); sp = {}
            for t, v, a in zip(e.input_ids[b].tolist(), w[b].tolist(), e.attention_mask[b].tolist()):
                if a and t not in skip and v > 0:
                    sp[t] = max(sp.get(t, 0.0), v)
            sparse.append(sp)
    return np.stack(dense), sparse
docs, owner = [], []
for lid, row in out.items():
    if row['keywords']:
        docs.append(' · '.join(row['keywords'])); owner.append(lid)
    for x in row['questions']:
        docs.append(x); owner.append(lid)
DV, DS = enc(docs)
_, QS = enc(p['texts'])
inv = {}
for i, sp in enumerate(DS):
    for t, v in sp.items():
        inv.setdefault(t, []).append((i, v))
inv = {t: (np.array([a for a, _ in x]), np.array([b for _, b in x], dtype=np.float32)) for t, x in inv.items()}
idx = {}
for i, o in enumerate(owner):
    idx.setdefault(o, []).append(i)
res = {}
for t, sp in zip(p['texts'], QS):
    s = np.zeros(len(docs), dtype=np.float32)
    for tok_id, v in sp.items():
        if tok_id in inv:
            s[inv[tok_id][0]] += v * inv[tok_id][1]
    res[t] = [round(float(np.sort(s[idx[o]])[::-1][:3].sum()) if o in idx else 0.0, 4) for o in p['owners']]
np.savez_compressed('d2q_dense.npz', d2q=DV)
json.dump({'d2q_docs': docs, 'd2q_owner': owner, 'sparse_d2q': res}, open('d2q_lexical.json', 'w'), ensure_ascii=False)
print('done', len(docs), time.time() - t0)
'''
nb = {'cells': [{'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': code.strip().splitlines(True)}],
      'metadata': {'accelerator': 'GPU', 'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'}, 'gpuhub': {'inputs': ['packet.json']}}, 'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open(sys.argv[1], 'w'))
