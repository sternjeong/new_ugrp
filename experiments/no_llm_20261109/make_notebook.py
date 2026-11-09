import json, sys
code = r'''
import gc, glob, json, os, re, subprocess, sys, time, traceback
import numpy as np, torch
import torch.nn.functional as F
assert torch.cuda.is_available()
p = json.load(open(glob.glob('/kaggle/input/**/packet.json', recursive=True)[0]))
log = {}
def stage(name, fn):
    t0 = time.time()
    try:
        fn(); log[name] = {'ok': True, 's': round(time.time() - t0, 1)}
    except Exception:
        log[name] = {'ok': False, 'error': traceback.format_exc()[-1500:]}
    print(name, log[name], flush=True)
    json.dump(log, open('stage_log.json', 'w'))
    gc.collect(); torch.cuda.empty_cache()

def d2q():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = 'Qwen/Qwen2.5-7B-Instruct'
    tok = AutoTokenizer.from_pretrained(name, padding_side='left')
    m = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.float16, device_map={'': 0}).eval()
    ask = """다음은 대학 연구실 정보입니다. 이 연구실을 찾을 학부생이 검색창에 쓸 법한 표현을 만드세요.
JSON만 출력하세요: {"keywords": [...], "questions": [...]}
- keywords: 이 연구실의 연구를 가리키는 한국어 연구 용어와 쉬운 일상어 12개.
- questions: 연구 용어를 모르는 학생이 이 연구와 관련해 일상에서 품을 만한 짧은 궁금증 6개 (예: '왜 ~할까요').
정보에 없는 분야를 지어내지 마세요.

연구실 정보: """
    out, bad = {}, []
    cards = p['cards']
    for i in range(0, len(cards), 8):
        batch = cards[i:i + 8]
        prompts = [tok.apply_chat_template([{'role': 'user', 'content': ask + c['text']}], tokenize=False, add_generation_prompt=True) for c in batch]
        enc = tok(prompts, return_tensors='pt', padding=True).to('cuda')
        with torch.no_grad():
            gen = m.generate(**enc, max_new_tokens=420, do_sample=False)
        for c, row in zip(batch, gen):
            text = tok.decode(row[enc.input_ids.shape[1]:], skip_special_tokens=True)
            try:
                d = json.loads(text[text.index('{'):text.rindex('}') + 1])
                out[c['lab_id']] = {'keywords': [str(x) for x in d['keywords']][:14], 'questions': [str(x) for x in d['questions']][:8]}
            except Exception:
                bad.append(c['lab_id']); out[c['lab_id']] = {'keywords': re.findall(r'"([^"]{2,30})"', text)[:14], 'questions': []}
        print('d2q', i, flush=True)
        json.dump({'labs': out, 'failed_json': bad}, open('d2q.json', 'w'), ensure_ascii=False)

def translate():
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    name = 'facebook/nllb-200-distilled-600M'
    tok = AutoTokenizer.from_pretrained(name, src_lang='kor_Hang')
    m = AutoModelForSeq2SeqLM.from_pretrained(name, torch_dtype=torch.float16).cuda().eval()
    out, ms = {}, []
    bos = tok.convert_tokens_to_ids('eng_Latn')
    for t in p['translate']:
        if not re.search('[가-힣]', t):
            out[t] = ''; continue
        t0 = time.time()
        enc = tok(t, return_tensors='pt', truncation=True, max_length=200).to('cuda')
        with torch.no_grad():
            gen = m.generate(**enc, forced_bos_token_id=bos, max_new_tokens=120)
        out[t] = tok.decode(gen[0], skip_special_tokens=True); ms.append(time.time() - t0)
    json.dump({'translations': out, 'median_s': float(np.median(ms))}, open('translations.json', 'w'), ensure_ascii=False)

HYP = {'research': '연구 주제나 과학적 궁금증', 'chat': '일상 잡담', 'procedure': '지원이나 신청 절차', 'vague': '주제를 알 수 없는 막연한 말'}
def nli():
    from transformers import pipeline
    pipe = pipeline('zero-shot-classification', model='MoritzLaurer/mDeBERTa-v3-base-mnli-xnli', device=0, torch_dtype=torch.float16)
    texts = sorted(set(p['all_queries']) | {x for v in p['exemplars'].values() for x in v})
    res = pipe(texts, list(HYP.values()), hypothesis_template='이 문장의 내용은 {}이다.', multi_label=False, batch_size=32)
    inv = {v: k for k, v in HYP.items()}
    json.dump({r['sequence']: {inv[l]: round(float(s), 4) for l, s in zip(r['labels'], r['scores'])} for r in res}, open('nli.json', 'w'), ensure_ascii=False)

state = {}
def m3():
    from huggingface_hub import snapshot_download
    from transformers import AutoModel, AutoTokenizer
    snap = snapshot_download('BAAI/bge-m3')
    tok = AutoTokenizer.from_pretrained(snap)
    m = AutoModel.from_pretrained(snap, torch_dtype=torch.float16).cuda().eval()
    sl = torch.nn.Linear(1024, 1); sl.load_state_dict(torch.load(snap + '/sparse_linear.pt', map_location='cpu')); sl = sl.half().cuda().eval()
    cl = torch.nn.Linear(1024, 1024); cl.load_state_dict(torch.load(snap + '/colbert_linear.pt', map_location='cpu')); cl = cl.half().cuda().eval()
    skip = {tok.cls_token_id, tok.eos_token_id, tok.pad_token_id, tok.unk_token_id}
    def enc(texts, bs=32, colbert=False):
        order = np.argsort([len(t) for t in texts])
        dense, sparse, cols = [None] * len(texts), [None] * len(texts), [None] * len(texts)
        for i in range(0, len(texts), bs):
            ids = order[i:i + bs]
            e = tok([texts[j] for j in ids], padding=True, truncation=True, max_length=512, return_tensors='pt').to('cuda')
            with torch.no_grad():
                h = m(**e).last_hidden_state
                d = F.normalize(h[:, 0], dim=-1).float().cpu().numpy()
                w = torch.relu(sl(h)).squeeze(-1)
                c = F.normalize(cl(h[:, 1:]) * e.attention_mask[:, 1:].unsqueeze(-1), dim=-1) if colbert else None
            for b, j in enumerate(ids):
                dense[j] = d[b]
                sp = {}
                for t, v, a in zip(e.input_ids[b].tolist(), w[b].tolist(), e.attention_mask[b].tolist()):
                    if a and t not in skip and v > 0:
                        sp[t] = max(sp.get(t, 0.0), v)
                sparse[j] = sp
                if colbert:
                    cols[j] = c[b][:int(e.attention_mask[b].sum()) - 1].cpu().numpy()
        return np.stack(dense), sparse, cols
    T0 = time.time()
    V, SP, C = enc(p['chunks'], 16, colbert=True)
    print('chunks', V.shape, time.time() - T0, flush=True)
    lab_kinds = {'profile', 'intro', 'paper'}
    owners = sorted({o for o, k in zip(p['owners'], p['kinds']) if k in lab_kinds})
    pos = {o: i for i, o in enumerate(owners)}
    idx = {o: np.array([i for i, (x, k) in enumerate(zip(p['owners'], p['kinds'])) if x == o and k in lab_kinds]) for o in owners}
    W = np.array([1.0, 0.3, 0.15])
    def agg(s, ids=None):
        out = []
        for o in owners:
            top = np.sort(s[idx[o]])[::-1][:3]
            out.append(float((W[:len(top)] * top).sum()))
        return out
    inv = {}
    for i, sp in enumerate(SP):
        for t, v in sp.items():
            inv.setdefault(t, []).append((i, v))
    inv = {t: (np.array([a for a, _ in x]), np.array([b for _, b in x], dtype=np.float32)) for t, x in inv.items()}
    def sparse_scores(sp, table, n):
        s = np.zeros(n, dtype=np.float32)
        for t, v in sp.items():
            if t in table:
                s[table[t][0]] += v * table[t][1]
        return s
    # dense for everything the strategies combine locally
    ex = [x for v in p['exemplars'].values() for x in v]
    d2q_docs, d2q_owner = [], []
    if os.path.exists('d2q.json'):
        for lid, row in json.load(open('d2q.json'))['labs'].items():
            if row['keywords']:
                d2q_docs.append(' · '.join(row['keywords'])); d2q_owner.append(lid)
            for x in row['questions']:
                d2q_docs.append(x); d2q_owner.append(lid)
    tr = json.load(open('translations.json'))['translations'] if os.path.exists('translations.json') else {}
    variants = {}
    for t in p['retrieve_texts']:
        variants[t] = [t] + ([f'{t} {tr[t]}'] if tr.get(t) else [])
    all_texts = sorted(set(p['dense_texts']) | {x for v in variants.values() for x in v})
    Q, QS, QC = enc(all_texts, 32, colbert=True)
    np.savez_compressed('dense.npz', texts=np.array(all_texts), q=Q, vocab=enc(p['vocab'], 64)[0], exemplars=enc(ex, 64)[0], d2q=enc(d2q_docs, 64)[0] if d2q_docs else np.zeros((0, 1024)))
    json.dump({'owners': owners, 'exemplar_texts': ex, 'd2q_docs': d2q_docs, 'd2q_owner': d2q_owner}, open('dense_meta.json', 'w'), ensure_ascii=False)
    # the service's phrase x lab-document similarities (A0, A4)
    D, _, _ = enc(p['docs'], 32)
    E, _, _ = enc(p['doc_phrases'], 32)
    S = E @ D.T
    sims = np.maximum.reduceat(S, np.array(p['starts']), axis=1)
    ends = list(p['starts'][1:]) + [S.shape[1]]
    best = np.full(sims.shape, -1, dtype=int)
    for li, (a, b) in enumerate(zip(p['starts'], ends)):
        cols = [k for k in range(a, b) if p['topic_of'][k] >= 0]
        if cols:
            arg = S[:, cols].argmax(axis=1)
            best[:, li] = [p['topic_of'][cols[j]] for j in arg]
    json.dump({'lab_ids': p['lab_ids'], 'sims': {x: [round(float(v), 5) for v in sims[i]] for i, x in enumerate(p['doc_phrases'])}, 'best': {x: [int(v) for v in best[i]] for i, x in enumerate(p['doc_phrases'])}}, open('doc_sims.json', 'w'), ensure_ascii=False)
    print('dense done', time.time() - T0, flush=True)
    # sparse and ColBERT
    d2q_idx = {}
    for i, o in enumerate(d2q_owner):
        d2q_idx.setdefault(o, []).append(i)
    d2q_sp = enc(d2q_docs, 64)[1] if d2q_docs else []
    d2q_inv = {}
    for i, sp in enumerate(d2q_sp):
        for t, v in sp.items():
            d2q_inv.setdefault(t, []).append((i, v))
    d2q_inv = {t: (np.array([a for a, _ in x]), np.array([b for _, b in x], dtype=np.float32)) for t, x in d2q_inv.items()}
    sp_out, col_out, sp_d2q = {}, {}, {}
    for i, t in enumerate(all_texts):
        s = sparse_scores(QS[i], inv, len(V))
        sp_out[t] = [round(x, 4) for x in agg(s)]
        if d2q_docs:
            sd = sparse_scores(QS[i], d2q_inv, len(d2q_docs))
            sp_d2q[t] = [round(float(np.sort(sd[d2q_idx[o]])[::-1][:3].sum()) if o in d2q_idx else 0.0, 4) for o in owners]
        top = np.argsort(V @ Q[i])[::-1][:200]
        q = torch.tensor(QC[i]).cuda()
        chunk_score = np.full(len(V), -1.0, dtype=np.float32)
        for k in top:
            d = torch.tensor(C[int(k)]).cuda()
            chunk_score[int(k)] = float((q @ d.T).max(dim=1).values.mean())
        col = []
        for o in owners:
            vals = np.sort(chunk_score[idx[o]])[::-1][:3]
            vals = vals[vals > -1]
            col.append(round(float((W[:len(vals)] * vals).sum()), 4) if len(vals) else 0.0)
        col_out[t] = col
    json.dump({'owners': owners, 'sparse': sp_out, 'colbert': col_out, 'sparse_d2q': sp_d2q}, open('lexical.json', 'w'), ensure_ascii=False)
    print('lexical done', time.time() - T0, flush=True)
    state.update(V=V, idx=idx, owners=owners, Q=Q, all_texts=all_texts, variants=variants)
    del m, sl, cl, C

def rerank():
    from sentence_transformers import CrossEncoder
    ce = CrossEncoder('BAAI/bge-reranker-v2-m3', max_length=512, device='cuda')
    ce.model.half()
    V, idx, owners, Q, all_texts, variants = (state[k] for k in ('V', 'idx', 'owners', 'Q', 'all_texts', 'variants'))
    where = {t: i for i, t in enumerate(all_texts)}
    out = {}
    for texts in variants.values():
        for t in texts:
            s = V @ Q[where[t]]
            pairs = [(t, '\n'.join(p['chunks'][int(k)] for k in idx[o][np.argsort(s[idx[o]])[::-1][:3]])[:1600]) for o in owners]
            out[t] = [round(float(x), 4) for x in ce.predict(pairs, batch_size=48, show_progress_bar=False)]
    json.dump({'owners': owners, 'scores': out}, open('rerank.json', 'w'), ensure_ascii=False)

for name, fn in (('d2q', d2q), ('translate', translate), ('nli', nli), ('m3', m3), ('rerank', rerank)):
    stage(name, fn)
print(json.dumps(log)[:3000])
'''
nb = {'cells': [{'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': code.strip().splitlines(True)}],
      'metadata': {'accelerator': 'GPU', 'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}, 'language_info': {'name': 'python'}, 'gpuhub': {'inputs': ['packet.json']}}, 'nbformat': 4, 'nbformat_minor': 5}
json.dump(nb, open(sys.argv[1], 'w'))
