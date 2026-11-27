"""관심 문장 → 연구실 검색 엔진 (표준 라이브러리만 사용).

experiments/query_understanding의 제안 파이프라인(L0~L4)을 서비스용으로 옮긴 것이다.
  L0 정규화 → L1 의도 분기 → L2 좋아함/싫어함 해석 → L3 사전 검색 + 임베딩 순위 융합(RRF) → L4 확신도 검사
임베딩 유사도는 EmbedBroker가 워커(Kaggle GPU의 bge-m3)에서 받아 온다. 워커가 없으면 해석을 반영한 사전 검색으로 후퇴한다.
확신도가 낮은 질의(uncertain)는 외부 LLM 라우터(Gemini)로 넘길 후보이며, 지금은 결과와 함께 '이해한 내용'을 보여 준다.
"""
import re
from collections import defaultdict

TOP_N = 10
# 개발용 질의 39개에서 10퍼센타일로 정한 값(experiments/query_understanding/V2/thresholds_v2.json). bge-m3 유사도 기준.
PHRASE_THRESHOLD = 0.529
QUERY_THRESHOLD = 0.539
RRF_K = 10
LAMBDA = 1.0

# ---- L2 규칙 해석 (experiments/query_understanding/rule_interpreter.py와 같은 규칙) ----
NEG = r'(?:^|(?<=[\s,]))(?P<neg>(?:(?!(?:는데|은데|한데|인데|지만|그리고|그런데)[\s,])[^,])+?)\s*(?:은|는|이|가)?\s*(?:싫(?:은데|고|지만|어서?)|별로(?:고|인데|지만|예|에|임|였(?:고|어요?|음)?)?|관심\s*없(?:고|는데|음|어요?)?|질렸(?:고|는데|어요?|음)?|질려서?|어렵(?:고|지만)|어려워서?|어려웠(?:고|어요?|음|는데)?|별로였(?:고|어요?|음)?|자신\s*(?:이\s*)?없(?:음|어요?|고|는데)?|지루했(?:고|어요?|음|는데)?|지루해서?|빼고|제외하고)\s*'
TAIL = re.compile(r'(?:\S*고\s*싶\S*|(?:은|는|이|가)?\s*좋(?:아|은데|고)\S*|(?:을|를)?\s*(?:하고|해보고|해\s*보고|공부하고|연구하고|알고|알아보고|만들고|배우고)\s*싶\S*|에?\s*(?:도\s*)?관심\s*(?:이\s*)?(?:있|많)\S*|(?:이|가|은|는)\s*(?:궁금|재밌|재미있|좋|더\s*끌려|끌려)\S*|(?:이|가|은|는)?(?<!더)(?<!더\s)\s*(?:(?:정말|진짜|너무|제일|가장)\s+)?(?:재밌|재미있|흥미로웠|흥미롭|좋았)(?!\S*지만)\S*(?:\s*보\S*)?|(?:을|를)?\s*(?:합친|같이|함께)\s*(?:연구)?(?:를)?|둘\s*다|(?:이|가)?\s*더\s*좋\S*|(?:이|가)\s*궁금\S*)')
TRAIL_PART = re.compile(r'(?:으로|에서|이나|이랑|쪽이|쪽은|쪽을|쪽|은|는|이|가|을|를|도|에|과|와|랑|나)$')
SPLIT = re.compile(r'\s*(?:과|와|랑|이랑|이나|나|및|,)\s+(?=\S)')


def _phrases(s):
    s = TAIL.sub(' ', s)
    s = re.sub(r'\b(?:나는|저는|제가|난|직접|이번엔|이미|더|쪽은?)\b', ' ', s)
    out = []
    for p in SPLIT.split(s.strip()):
        p = re.sub(r'\s+', ' ', p).strip(' ,')
        p = TRAIL_PART.sub('', p).strip()
        if p:
            out.append(p)
    return out


def interpret(text):
    t = re.sub(r'[.!?]+$', '', text.strip())
    t = re.sub(r'요$', '', t)
    m = re.search(r'(?P<a>.+?)\s*(?:보다는|보다|말고)\s*(?P<b>.+)', t)
    if m:
        # Only the clause right before 보다는 is set aside: in '알고리즘 수업이 재밌었는데 이론보다는 …' the class stays a like.
        *before, a = re.split(r'(?<=는데|은데|한데|지만|[있좋싶었았였]고)\s+|,\s*', m.group('a'))
        return {'likes': _phrases(' '.join(before)) + _phrases(m.group('b')), 'dislikes': _phrases(a)}
    dislikes = []

    def grab(mm):
        dislikes.extend(_phrases(mm.group('neg')))
        return ' '
    rest = re.sub(NEG, grab, t)
    return {'likes': _phrases(rest), 'dislikes': dislikes}


# ---- L0 정규화 ----
# A Latin abbreviation ends at the next non-Latin character, so 'cv랑' and 'llm은' still match (\b does not:
# Korean letters count as word characters).
_W = lambda word: rf'(?<![A-Za-z0-9]){word}(?![A-Za-z0-9])'
SYN = [
    (r'챗\s*지피티|챗\s*GPT|chatgpt|지피티|' + _W('GPT'), '언어모델'),
    (r'거대\s*언어\s*모델|' + _W('LLMs?') + '|엘엘엠', '언어모델'),
    (r'컴퓨터\s*아키텍처|아키텍처', '컴퓨터 구조'),
    (r'머신\s*러닝', '머신러닝'),
    (r'딥\s*러닝', '딥러닝'),
    (r'로보틱스|로봇공학', '로봇'),
    (_W('CV') + '|씨브이', '컴퓨터 비전'),
    (_W('NLP') + '|엔엘피', '자연어처리'),
    (_W('RL'), '강화학습'),
    (_W('DB') + '|디비', '데이터베이스'),
    (_W('ML'), '머신러닝'),
    (_W('SW') + '|' + _W('S/W'), '소프트웨어'),
    (_W('IoT'), '사물인터넷'),
    (r'자율\s*주행차?|자동\s*운전', '자율주행'),
    (_W('HCI'), '인간-컴퓨터 상호작용'),
    (_W('OS') + '|오에스|(?<![가-힣])운체(?![계가-힣])', '운영체제'),
    (r'(?<![가-힣])컴구(?![름가-힣])', '컴퓨터구조'),
    (_W('VR') + '|' + _W('AR') + '|' + _W('XR'), '가상현실'),
]


def normalize(text):
    t = re.sub(r'(?:[ㅋㅎㅠㅜ]){2,}|[ㄱ-ㅎㅏ-ㅣ]+(?=\s|$)', ' ', text)  # chat noise such as ㅋㅋ, ㅠㅠ
    t = re.sub(r'\s+', ' ', t.strip())
    for pat, rep in SYN:
        t = re.sub(pat, rep, t, flags=re.I)
    return re.sub(r'(?<!\S)(\S+)(?:\s+\1)+(?!\S)', r'\1', t)  # "LLM 언어모델" → "언어모델 언어모델" → "언어모델"


# ---- L1 의도 분기 ----
CAREER = re.compile(r'(대학원|진학|인턴|컨택|교수님께|메일|이메일|신청|지원|장학금|학점|추천서|취업|진로|상담|면담|연락|입시|면접|석사|박사|유학)')
OUT_OF_SCOPE = re.compile(r'(화학|유기|생물|생명과학|의학|의대|약학|경제|경영|법학|심리|철학|역사|문학|천문|우주|지질|물리학|수학과|건축|토목|화공|환경|식품|농업)')
BROAD = {'컴퓨터', 'ai', '인공지능', '전자', '전기', '공학', '소프트웨어', '하드웨어', 'it', '기술', '과학', '이공계', '코딩', '프로그래밍', '공부', '연구', '컴퓨터공학', '전자공학', '전기전자'}
PRIORITY = re.compile(r'(지만|괜찮은데|괜찮지만|이미\s*해봐|해봤|해봐서|그나마|굳이|하긴|그래도|더\s*(끌|좋|관심)|보다\s*더|아니면|정도는)')
NEG_CUE = re.compile(r'(싫|별로|관심\s*없|질렸|질려|어렵|빼고|제외|말고|안\s*맞|흥미\s*없|재미없)')

MESSAGES = {
    'too_broad': '조금 더 구체적으로 적어 주시면 더 잘 찾을 수 있어요. 예를 들어 컴퓨터 구조, 운영체제, 보안, 네트워크, 인공지능처럼 궁금한 부분을 하나 골라 적어 보세요.',
    'career': '연구실에 들어가는 방법이나 진로 절차보다는, 관심 분야로 연구실을 찾아 드리는 서비스예요. 관심 있는 분야나 재미있었던 수업을 적어 주세요.',
    'out_of_scope': '현재 자료는 컴퓨터공학·전자전기·IT융합·반도체공학 연구실에 한정되어 있어요. 말씀하신 분야는 아직 포함되지 않았을 수 있어요. 관련된 다른 표현으로 적어 보셔도 좋아요.',
    'nonsense': '관심 분야나 궁금한 점을 문장으로 적어 주세요. 예: 로봇이 스스로 움직이는 게 신기해요.',
    'need_likes': '싫은 주제는 알겠어요. 어떤 주제가 궁금한지도 함께 적어 주세요.',
}


def is_nonsense(t):
    if not re.search(r'[가-힣]', t):
        return len(re.sub(r'[^A-Za-z0-9]', '', t)) < 2
    return len(re.sub(r'[^가-힣A-Za-z0-9]', '', t)) < 2


def broad_only(likes):
    return bool(likes) and all(re.sub(r'\s+', '', p).lower() in BROAD for p in likes)


def plan(text, catalog):
    """L0~L2: 임베딩이 필요 없는 부분."""
    t = normalize(text)
    out = {'norm': t, 'flags': [], 'likes': [], 'dislikes': []}
    if is_nonsense(t):
        out['intent'] = 'nonsense'
        return out
    it = interpret(t)
    likes, dislikes = it['likes'], it['dislikes']
    concepts = catalog.concepts_in(t)
    out.update(likes=likes, dislikes=dislikes)
    if CAREER.search(t) and not concepts:
        out['intent'] = 'career'
    elif OUT_OF_SCOPE.search(t) and not concepts:
        out['intent'] = 'out_of_scope'
    elif broad_only(likes) and not dislikes:
        out['intent'] = 'too_broad'
    elif not likes and dislikes:
        out['intent'] = 'need_likes'
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
        out['phrase_concepts'] = {p: sorted(catalog.concepts_in(p)) for p in likes}
    return out


# ---- L3 순위 융합 ----
def rrf(*lists, k=RRF_K):
    score = defaultdict(float)
    for lst in lists:
        for i, item in enumerate(lst):
            score[item] += 1 / (k + i + 1)
    return [item for item, _ in sorted(score.items(), key=lambda kv: -kv[1])]


def zscores(values):
    n = len(values)
    mean = sum(values) / n
    sd = (sum((v - mean) ** 2 for v in values) / n) ** 0.5 + 1e-9
    return [(v - mean) / sd for v in values]


def with_particle(word):
    """'과' after a Korean final consonant, otherwise '와'."""
    last = (word or ' ').rstrip()[-1:]
    return '과' if '가' <= last <= '힣' and (ord(last) - 0xAC00) % 28 else '와'


class QueryEngine:
    def __init__(self, catalog, broker=None, timeout=6.0, launcher=None):
        self.catalog = catalog
        self.broker = broker
        self.timeout = timeout
        self.launcher = launcher
        self.primary = {lid: {t['concept'] for t in catalog.primary_topics(lid)} for lid in catalog.profiles}

    # 해석을 반영한 사전 검색: 싫어함 개념을 가진 연구실은 뒤로 보낸다
    def dictionary_cards(self, plan_, text):
        base = self.catalog.search(' '.join(plan_['likes']) or text)
        bad = set()
        for d in plan_['dislikes']:
            bad |= self.catalog.concepts_in(d)
        front = [c for c in base if not (self.primary.get(c['id'], set()) & bad)]
        back = [c for c in base if self.primary.get(c['id'], set()) & bad]
        return front + back

    def embedding_ranking(self, plan_, sims):
        """sims: {구절: {'sims': {lab_id: float}, 'best': {lab_id: 주제 번호}}} → (순위 목록, 유사도 점수, 근거 구절)"""
        likes = plan_['likes'] or [plan_['norm']]
        lab_ids = [lid for lid in sims[likes[0]]['sims'] if lid in self.catalog.profiles]
        if not lab_ids:
            return [], {}, {}
        z_like = [zscores([sims[p]['sims'][lid] for lid in lab_ids]) for p in likes]
        score = [sum(col) / len(col) for col in zip(*z_like)]
        if plan_['dislikes']:
            pen = [max(0.0, max(col)) for col in zip(*[[max(0.0, v) for v in zscores([sims[p]['sims'][lid] for lid in lab_ids])] for p in plan_['dislikes']])]
            score = [s - LAMBDA * q for s, q in zip(score, pen)]
        order = sorted(range(len(lab_ids)), key=lambda i: -score[i])
        ranking = [lab_ids[i] for i in order]
        why = {}
        for i in order:
            lid = lab_ids[i]
            best_phrase = max(likes, key=lambda p: sims[p]['sims'][lid])
            why[lid] = (best_phrase, sims[best_phrase]['best'].get(lid, -1))
        return ranking, {lab_ids[i]: score[i] for i in order}, why

    def semantic_card(self, lab_id, score, why):
        card = self.catalog.card(lab_id)
        phrase, topic_index = why
        topics = self.catalog.profiles[lab_id]['topics']
        evidence = [self.catalog._evidence(topics[topic_index])] if 0 <= topic_index < len(topics) else []
        card.update(matched_topics=[], evidence=evidence, score=round(score, 3), connection='semantic',
                    reason=f"‘{phrase}’{with_particle(phrase)} 의미가 가까운 내용을 연구실 자료에서 찾았습니다. 실제 활용 관계는 원문에서 확인하세요.")
        if card['status'] == 'thin':
            card['reason'] += ' 수집 자료가 제목 수준이라 연구 내용은 홈페이지에서 확인이 필요합니다.'
        return card

    def search(self, text):
        plan_ = plan(text, self.catalog)
        result = {'labs': [], 'intent': plan_['intent'], 'mode': 'none', 'message': MESSAGES.get(plan_['intent']),
                  'interpretation': {'likes': plan_['likes'], 'dislikes': plan_['dislikes']}, 'uncertain': False, 'reasons': []}
        if plan_['intent'] != 'search':
            return result
        dict_cards = self.dictionary_cards(plan_, text)
        by_id = {c['id']: c for c in dict_cards}
        if self.launcher and self.broker and not self.broker.available() and self.launcher.ensure_started():
            result.update(labs=dict_cards, mode='starting', message='의미 검색을 준비하고 있어요. 잠시만 기다려 주세요.')
            return result
        likes = plan_['likes'] or [plan_['norm']]
        phrases = list(dict.fromkeys(likes + plan_['dislikes'] + [plan_['norm']]))
        sims = self.broker.request(phrases, self.timeout) if self.broker else None
        if sims is not None and any(p not in sims for p in phrases):
            sims = None                        # 워커 응답이 불완전하면 사용하지 않는다
        if sims is None:                       # 워커 없음/지연 → 해석을 반영한 사전 검색
            result.update(labs=dict_cards, mode='dictionary')
            result['reasons'] = plan_['flags']
            result['uncertain'] = bool(plan_['flags'])
            return result
        reasons = list(plan_['flags'])
        for p in plan_['likes']:
            if not plan_['phrase_concepts'].get(p) and max(sims[p]['sims'].values()) < PHRASE_THRESHOLD:
                reasons.append('unmatched_phrase')
        if not dict_cards and max(sims[plan_['norm']]['sims'].values()) < QUERY_THRESHOLD:
            reasons.append('weak_query')
        ranking, scores, why = self.embedding_ranking(plan_, sims)
        fused = rrf([c['id'] for c in dict_cards], ranking) if dict_cards else ranking
        labs = []
        for lid in fused[:TOP_N]:
            labs.append(by_id[lid] if lid in by_id else self.semantic_card(lid, scores.get(lid, 0.0), why[lid]))
        result.update(labs=labs, mode='embedding', reasons=sorted(set(reasons)), uncertain=bool(reasons))
        return result
