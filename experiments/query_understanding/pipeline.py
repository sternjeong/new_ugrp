"""제안 파이프라인 (L0~L4). 표준 라이브러리 + 앱 코드만 사용하고, 임베딩 유사도는 외부에서 계산한 값을 받는다.
L0 정규화 → L1 의도 분기 → L2 해석(좋아함/싫어함, 불확실 표시) → L3 검색(사전 + 임베딩 순위 융합) → L4 확신도 검사(라우터 호출 여부).
라우터(Gemini)는 호출 여부만 기록한다. 결과를 튜닝할 수 없는 구간이므로 호출했다는 사실로 끝낸다."""
import re, sys, collections as C
sys.path.insert(0, '.')
sys.path.insert(0, 'experiments/query_understanding')
from rule_interpreter import interpret

# ---- L0 정규화: 자주 쓰는 표현을 앱 사전이 아는 말로 ----
SYN = [
    (r'챗\s*지피티|챗\s*GPT|chatgpt|지피티|\bGPT\b', '언어모델'),
    (r'거대\s*언어\s*모델|\bLLM\b|엘엘엠', '언어모델'),
    (r'컴퓨터\s*아키텍처|아키텍처', '컴퓨터 구조'),
    (r'머신\s*러닝', '머신러닝'),
    (r'딥\s*러닝', '딥러닝'),
    (r'로보틱스|로봇공학', '로봇'),
    (r'\bCV\b|씨브이', '컴퓨터 비전'),
    (r'\bNLP\b|엔엘피', '자연어처리'),
    (r'자율\s*주행차?|자동\s*운전', '자율주행'),
    (r'\bHCI\b', '인간-컴퓨터 상호작용'),
    (r'\bVR\b|\bAR\b|\bXR\b', '가상현실'),
]

def normalize(text):
    t = re.sub(r'\s+', ' ', text.strip())
    for pat, rep in SYN:
        t = re.sub(pat, rep, t, flags=re.I)
    return t

# ---- L1 의도 분기 ----
CAREER = re.compile(r'(대학원|진학|인턴|컨택|교수님께|메일|이메일|신청|지원|장학금|학점|추천서|취업|진로|상담|면담|연락|입시|면접|석사|박사|유학)')
OUT_OF_SCOPE = re.compile(r'(화학|유기|생물|생명과학|의학|의대|약학|경제|경영|법학|심리|철학|역사|문학|천문|우주|지질|물리학|수학과|건축|토목|화공|환경|식품|농업)')
BROAD = {'컴퓨터', 'ai', '인공지능', '전자', '전기', '공학', '소프트웨어', '하드웨어', 'it', '기술', '과학', '이공계', '코딩', '프로그래밍', '공부', '연구', '컴퓨터공학', '전자공학', '전기전자'}
# 우선순위·대조·망설임 표현: 규칙이 좋아함/싫어함의 무게를 정확히 알 수 없다
PRIORITY = re.compile(r'(지만|괜찮은데|괜찮지만|이미\s*해봐|해봤|해봐서|그나마|굳이|하긴|그래도|더\s*(끌|좋|관심)|보다\s*더|아니면|정도는)')
NEG_CUE = re.compile(r'(싫|별로|관심\s*없|질렸|질려|어렵|빼고|제외|말고|안\s*맞|흥미\s*없|재미없)')

def is_nonsense(t):
    if not re.search(r'[가-힣]', t):
        letters = re.sub(r'[^A-Za-z0-9]', '', t)
        return len(letters) < 2
    return len(re.sub(r'[^가-힣A-Za-z0-9]', '', t)) < 2

def broad_only(likes):
    return bool(likes) and all(re.sub(r'\s+', '', p).lower() in BROAD for p in likes)

def plan(text, cat):
    """질의 하나의 L0~L2 결과. 임베딩이 필요 없는 부분만 계산한다."""
    t = normalize(text)
    out = {'raw': text, 'norm': t, 'flags': []}
    if is_nonsense(t):
        out.update(intent='nonsense', likes=[], dislikes=[])
        return out
    it = interpret(t)
    likes, dislikes = it['likes'], it['dislikes']
    concepts = cat.concepts_in(t)
    out.update(likes=likes, dislikes=dislikes, concepts=sorted(concepts))
    if CAREER.search(t) and not concepts:
        out['intent'] = 'career'
    elif OUT_OF_SCOPE.search(t) and not concepts:
        out['intent'] = 'out_of_scope'
    elif broad_only(likes) and not dislikes:
        out['intent'] = 'too_broad'
    else:
        out['intent'] = 'search'
        if not likes:
            out['flags'].append('no_likes')
        if NEG_CUE.search(t) and not dislikes:
            out['flags'].append('neg_cue_unparsed')
        if PRIORITY.search(t):
            out['flags'].append('priority')
        if len(t) > 70:
            out['flags'].append('long_input')
        out['phrase_concepts'] = {p: sorted(cat.concepts_in(p)) for p in likes}
    return out

# ---- L3 검색 ----
def rrf(*lists, k=10):
    s = C.defaultdict(float)
    for L in lists:
        for i, l in enumerate(L):
            s[l] += 1 / (k + i + 1)
    return [l for l, _ in sorted(s.items(), key=lambda x: -x[1])]

def dict_ranking(cat, likes, dislikes, text):
    base = [r['id'] for r in cat.search(' '.join(likes) or text)]
    bad = set()
    for d in dislikes:
        bad |= cat.concepts_in(d)
    prof = {lid: {t['concept'] for t in cat.profiles[lid]['topics'] if t.get('weight', 'primary') == 'primary'} for lid in cat.profiles}
    return [l for l in base if not (prof[l] & bad)] + [l for l in base if prof[l] & bad]
