"""Positive/negative query interpretation over the new curated catalog.

classify_curated_query splits the text into liked and disliked phrases or refuses it. RagQueryEngine (the
teammate's vectorRAG engine from engine/modules with R2 summaries, R5 reranker and R7 query rewrite, chosen by
ablation on 2026-11-26) then ranks labs from the worker's chunk scores. CuratedQueryEngine is the earlier engine
(dictionary + phrase embedding + the worker's whole-query analysis, fused by RRF); RagQueryEngine falls back to
its dictionary search when the worker is off.
"""
import re
from collections import OrderedDict

from .catalog import safe_urls
from .curated_catalog import COURSE_CUE, COURSE_WORD, EVIDENCE_KIND, clip, search_terms, snippet
from .embed_broker import query_key
from .query_engine import LAMBDA, QueryEngine, RRF_K, broad_only, interpret, is_nonsense, normalize, rrf, TOP_N, with_particle, zscores


PROCEDURE = re.compile(r'(수강\s*신청|대학원\s*(?:지원|입학|진학)|교수(?:님)?께?\s*(?:메일|이메일)|(?:지원|신청|컨택|면접|장학금|추천서).*(?:방법|어떻게|절차))')
PROCEDURE_QUESTION = re.compile(r'(어떻게|방법|절차|알려|해야|하나요|할까요|쓰나요|언제|가능할까|될까요|되나요)')
NEGATIVE_CUE = re.compile(r'(싫|별로|관심\s*없|좋아하지\s*않|흥미\s*없|재미없|빼고|제외|말고|보다)')
# A clause also ends at a note-style '…었음'/'…않음' with no period ('알고리즘 재밌었음 시스템 과목이 …').
# So do a polite '…어요/아요/해요' followed by more text, and '…었고' ('재밌었고 분산시스템도 궁금함').
CLAUSE_BREAK = re.compile(r'(?<=[.!?])\s+|\n+|(?<=싶고),\s*|(?<=좋고),\s*|(?<=[었았였겠했않없있싶좋같]음)[\s,]+|(?<=[가-힣][함됨듯])[\s,]+|(?<=[어아해]요)[\s,]+|(?<=[었았였]고)[\s,]+')
# A conjunction or '수업 들었는데' starts a new clause; otherwise a dislike after it reaches back over the likes
# ('의료영상 … 관심있어요 근데 생물학 공부는 하기싫어요' was read as one dislike and refused).
CONJUNCTION = re.compile(r'(?<!\S)(?:아\s+)?(?:근데|그런데|하지만|그치만|그렇지만|다만)(?!\S)|(?<!\S)(?:재밌게\s+|열심히\s+)?들었(?:고|는데|어요?|음)(?!\S)')
# '수학 안 싫어함', '머신러닝이 싫지는 않은데' are likes; '공부는 하기 싫어요' dislikes the subject, not '하기'.
NOT_DISLIKE = re.compile(r'\s*안\s*싫(?:어함|어요?|음|고|은데)|\s*싫(?:지\s*(?:는|도|만)?|진)\s*않(?:은데|아요?|고|음|지만)'
                         r'|\s*나쁘지\s*(?:는|도|만)?\s*않\S*|\s*괜찮았\S*|\s*(?:에|이|가)?\s*(?:꽂혔|신기하|땡겨|땡기|인상\s*깊)\S*')
# '피하고 싶어요', '진짜 안 맞음', '안 땡김' dislike what comes before.
AVOID = re.compile(r'\s*(?:은|는|을|를|이|가)?\s*(?:피하고\s*싶\S*|(?:진짜\s*|정말\s*|좀\s*)?안\s*(?:맞|땡기|땡겨|땡김)\S*)')
DO_DISLIKE = re.compile(r'(?:\s*(?:공부|연구)(?:는|은|도)?)?\s*하기\s*싫')
# Negations the rule parser does not know, rewritten to its '… 싫고' form:
# 'ai 까지 다루고 싶지는 않음' → 'ai 싫고', '수학은 별로 안 좋아해' → '수학 싫고'.
NOT_WANT = re.compile(r'(?:\s*(?:을|를|은|는|까지는?|도))?\s+(?:\S+고\s*)?싶지\s*(?:는|도|가)?\s*않(?:음|아요?|고|은데|는데|습니다|다|지만)?')
DONT_LIKE = re.compile(r'(?:\s*(?:은|는|이|가|도))?\s*(?:별로\s*)?안\s*좋아(?:해요?|함|하고|하는데|합니다|해서)?')
# Words that say nothing about a topic and would otherwise stay inside a liked phrase.
FILLER = re.compile(r'딱히\s*없\S*|(?:아직\s*)?(?:잘\s*)?모르겠\S*|관심\s*분야\S*|(?<=\s)등(?=\s|$)|[\U0001F300-\U0001FAFF☀-➿]+'
                    r'|(?<!\S)(?:저|오히려|그냥|좀|딱히|굳이|그리고|아니면|정도|요즘은?|음+\.*|이거|(?:이런|그런|저런)\s*(?:거|것)?|뭐든\S*|괜찮\S*|고르자면|꼽자면)(?!\S)'
                    r'|생각\s*중\S*'
                    # greetings, '컴공 2학년인데요', and procedure words beside an interest
                    r'|(?<!\S)(?:안녕하세요|안녕|반갑습니다|반가워요)\S*|(?<!\S)(?:저는?\s+)?\d\s*학년\S*'
                    r'|(?<!\S)(?:교수님께?|컨택\S*|메일\S*|학점\S*|대학원\S*|진학\S*)(?!\S)')
KEYBOARD_NOISE = re.compile(r'^(?:asdf|qwer|zxcv|ㅋㅋ+|ㅎㅎ+|ㅠㅠ+|ㅜㅜ+)$', re.I)
AVOID_ONLY = re.compile(r'피하고\s*싶')
AVOID_CUE = re.compile(r'피하고\s*싶|못\s*하겠|안\s*했으면')  # a stated avoidance the rule parser may miss; the refusal check reads it as 'only a dislike'
HAS_POSITIVE = re.compile(r'좋|재밌|관심|궁금|는데|지만')
INTEREST_CLAUSE = re.compile(r'좋|재밌|관심|궁금|는데|지만|(?<!피)하고\s*싶은데')
REQUEST_TAIL = re.compile(r'\s*(?:(?:같은|비슷한)\s*(?:거|것|걸)\s*(?:하는|다루는)?|(?:을|를|에|로|으로|은|는|이|가)?\s*(?:추천\s*해?\s*(?:주세|줘|주)?\S*|찾고\s*있\S*|찾아\S*|찾\S*|있을까\S*|있나\S*|있어\S*|있\S*|어디가?\s*맞을까\S*|어디\S*|뭐가?\s*\S*|해볼\s*수\s*\S*|해\s*보고\S*|궁금\S*|좋겠\S*)|(?:연구하는|다루는|하는)?\s*(?:곳|데|연구실|랩|쪽)|연구하는|다루는|하는)$')
QUOTABLE_PHRASE = 18
GATE_MARGIN = 0.05   # from leave-one-out on the worker's intent examples (experiments/no_llm_20261109/REPORT.md)
REFUSALS = {'off_topic': ('nonsense', '관심 있는 연구 주제나 문제를 적어 주세요.'),
            'procedure': ('career', '연구실 추천을 위한 관심 분야나 연구 문제를 적어 주세요.'),
            'too_vague': ('too_broad', '조금 더 구체적인 연구 주제나 문제를 적어 주세요.'),
            'only_dislike': ('need_likes', '궁금한 연구 주제도 함께 적어 주세요.')}
SEMANTIC_BACKING = 0.2   # a dictionary hit on ordinary words must also be in this top share of the embedding ranking
MIN_BACKING = 30


def clean_like(phrase):
    """Remove request wording from the end of a phrase ('방사선 연구하는 곳 있' -> '방사선')."""
    text = phrase.strip()
    for _ in range(6):
        new = REQUEST_TAIL.sub('', text).strip()
        if new == text or len(new) < 2:
            break
        text = new
    return text if len(text) >= 2 else phrase.strip()


def penalized_z(scores, penalties, liked=None):
    """{lab: z-scored score minus the z-score of each disliked subject where it is above average}. With liked
    ({lab: its liked-phrase similarity}) a lab pays only where it is at least as close to the dislike as to the likes: a broad
    dislike ('분산 시스템 … 머신러닝은 빼고') otherwise sank every computing lab and left power electronics on top."""
    labs = list(scores)
    if not labs:
        return {}
    total = dict(zip(labs, zscores([scores[lid] for lid in labs])))
    for penalty in penalties:
        z = dict(zip(labs, zscores([penalty.get(lid, 0.0) for lid in labs])))
        total = {lid: value - LAMBDA * max(0.0, z[lid]) * (liked is None or penalty.get(lid, 0.0) >= liked.get(lid, 0.0))
                 for lid, value in total.items()}
    return total


def penalized(scores, penalties, liked=None):
    """Labs by z-scored score, minus the z-score of each disliked subject where it is above average."""
    total = penalized_z(scores, penalties, liked)
    return sorted(total, key=lambda lid: -total[lid])


def notation(text):
    """'미생물 o / 동물실험 x' and 'computer vision but not NLP' in the parser's Korean form."""
    text = re.sub(r"(?i)\b(?:i'?m interested in|i am interested in|i like|i want to (?:study|do|work on))\s+", '', text)
    text = re.sub(r'(?i)\s+but\s+not\s+([^.,/]+)', r'. \1 싫고', text)
    text = re.sub(r'\s+[xX×✗]\s*(?=[/,]|$)', ' 싫고', text)
    text = re.sub(r'\s+[oO○]\s*(?=[/,]|$)', ' 좋고', text)
    return re.sub(r'\s*/\s*', ', ', text)


def classify_curated_query(text):
    """Decide whether a query may reach retrieval, independent of catalog matches."""
    norm = normalize(text)
    normalized_negative = re.sub(r'좋아하지\s*않(?:지만|아요|습니다|아)', '싫고', norm)
    normalized_negative = notation(normalized_negative)
    normalized_negative = DO_DISLIKE.sub(' 싫', NOT_DISLIKE.sub(' 좋고', normalized_negative))
    normalized_negative = AVOID.sub(' 싫고', normalized_negative)
    normalized_negative = DONT_LIKE.sub(' 싫고', NOT_WANT.sub(' 싫고', normalized_negative))
    normalized_negative = CONJUNCTION.sub('. ', normalized_negative)
    normalized_negative = re.sub(r'\s+', ' ', FILLER.sub(' ', normalized_negative)).strip()
    # Read each sentence (and each '…싶고,' clause) on its own: interpreted together, a long text collapses into one
    # phrase such as '로봇 비전 파이썬으로 빠르게 데모를 … 인턴이면 좋겠어' that matches nothing well.
    pieces = [x for x in CLAUSE_BREAK.split(normalized_negative) if x.strip()] or [normalized_negative]
    likes, dislikes = [], []
    for piece in pieces:
        parsed = interpret(piece.strip())
        likes += parsed['likes']
        dislikes += parsed['dislikes']
    likes, dislikes = list(dict.fromkeys(likes)), list(dict.fromkeys(dislikes))
    # '컴퓨터구조 수업' → '컴퓨터구조': the word 수업 alone pulls labs about learning and attention.
    likes = list(dict.fromkeys(re.sub(r'\s+', ' ', COURSE_WORD.sub(' ', p)).strip() or p for p in likes))
    refined = []
    for phrase in likes:
        phrase = re.sub(r'\s*듣고\s+', ' | ', phrase)
        phrase = re.sub(r'에\s*빠졌(?:어|다)?$', '', phrase)
        # Split an object and instrument only when they form a control-action sentence.
        if re.search(r'[을를]\s+\S+(?:으로|로)\s+제어하고\s*싶', norm):
            phrase = re.sub(r'(?<=\S)[을를]\s+(.+)$', r' | \1', phrase)
        refined.extend(part.strip() for part in phrase.split('|') if part.strip())
    likes = list(dict.fromkeys(refined))
    result = {'norm': norm, 'likes': likes, 'dislikes': dislikes,
              'intent': 'search', 'message': None, 'uncertain': False}
    if is_nonsense(norm) or KEYBOARD_NOISE.fullmatch(norm):
        result.update(intent='nonsense', likes=[], dislikes=[],
                      message='관심 있는 연구 주제나 문제를 적어 주세요.')
    elif PROCEDURE.search(norm) and PROCEDURE_QUESTION.search(norm):
        result.update(intent='career', message='연구실 추천을 위한 관심 분야나 연구 문제를 적어 주세요.')
    elif not likes and not dislikes:  # only hedging ('아직 잘 모르겠음 관심분야를'): nothing to search for
        result.update(intent='too_broad', message='조금 더 구체적인 연구 주제나 문제를 적어 주세요.')
    elif not likes and dislikes:
        result.update(intent='need_likes', message='궁금한 연구 주제도 함께 적어 주세요.')
    elif AVOID_ONLY.search(norm) and not HAS_POSITIVE.search(norm):
        result.update(intent='need_likes', message='궁금한 연구 주제도 함께 적어 주세요.')
    elif broad_only(likes):
        result.update(intent='too_broad', message='조금 더 구체적인 연구 주제나 문제를 적어 주세요.')
    elif NEGATIVE_CUE.search(normalized_negative) and not dislikes:
        result.update(intent='need_clarification', uncertain=True,
                      message='피하고 싶은 주제를 정확히 이해하지 못했어요. 좋아하는 주제와 피하고 싶은 주제를 나눠 적어 주세요.')
    result['likes'] = list(dict.fromkeys(clean_like(p) for p in result['likes']))
    return result


class CuratedQueryEngine(QueryEngine):
    def conflicts_with_dislikes(self, lab_id, dislikes):
        """Only reject explicit topic-label overlaps; do not infer hidden semantics."""
        labels = [topic['label_ko'].lower() for topic in self.catalog.profiles[lab_id]['topics']]
        # A Latin word matches whole words only: 'ai' must not reject 'Sustainable' or 'Markov Chains'.
        patterns = [re.compile(rf'(?<![a-z0-9]){re.escape(p.lower())}(?![a-z0-9])') if re.fullmatch(r'[a-z0-9 ]+', p.lower())
                    else re.compile(re.escape(p.lower())) for p in dislikes]
        return any(pattern.search(label) for pattern in patterns for label in labels)

    def dictionary_cards(self, plan_, text):
        cards = self.catalog.search(' '.join(plan_['likes']) or text)
        return [card for card in cards
                if not self.conflicts_with_dislikes(card['id'], plan_['dislikes'])]

    def search(self, text, allow_remote=True):
        parsed = classify_curated_query(text)
        norm, likes, dislikes = parsed['norm'], parsed['likes'], parsed['dislikes']
        result = {'labs': [], 'intent': parsed['intent'], 'mode': 'none',
                  'message': parsed['message'],
                  'interpretation': {'likes': likes, 'dislikes': dislikes},
                  'uncertain': parsed['uncertain'], 'reasons': []}
        if parsed['intent'] != 'search':
            return result
        plan_ = {'likes': likes, 'dislikes': dislikes, 'norm': norm}
        cards = self.dictionary_cards(plan_, text)
        by_id = {c['id']: c for c in cards}
        cue = bool(COURSE_CUE.search(norm))
        courses = self.catalog.courses_named(likes, cue)
        linked = {lid: link for lid, link in self.catalog.course_labs(courses).items()
                  if not self.conflicts_with_dislikes(lid, dislikes)}
        # Course-led only when every liked phrase names a class: a topic that merely shares a title
        # ('컴퓨터 구조와 시스템 보안') or a class mentioned beside other interests leaves the search in front.
        led = bool(linked) and all(self.catalog.courses_named([p], cue) for p in likes)
        if courses:
            result['courses'] = [{'code': c['code'], 'name': c['title']} for c, _ in courses]
        phrases = list(dict.fromkeys((likes or [norm]) + dislikes + [norm]))
        # The worker also reads the whole query: refusal, translation, chunk retrieval and reranking. A worker without those parts leaves it out.
        query = {'raw': text, 'text': ' '.join(likes) if dislikes and likes else text, 'dislikes': dislikes, 'gate': None if dislikes or (AVOID_CUE.search(norm) and INTEREST_CLAUSE.search(norm)) else GATE_MARGIN}
        understands = hasattr(self.broker, 'understand')
        needed = phrases + [query_key(query)] if understands else phrases
        cached = bool(self.broker) and hasattr(self.broker, 'cached') and self.broker.cached(needed)
        if (allow_remote and not cached and self.launcher and self.broker and not self.broker.available()
                and self.launcher.ensure_started()):
            result.update(labs=self.with_courses(self.fuse(linked, led, [c['id'] for c in cards]), by_id, linked, led),
                          mode='starting', message='의미 검색을 준비하고 있어요. 잠시만 기다려 주세요.')
            return result
        # Without consent to processing abroad, only similarities already cached on this server are used.
        where = {} if allow_remote else {'remote': False}
        sims = None
        if understands:
            sims = self.broker.understand(phrases, query, self.timeout, **where)
        elif self.broker:
            sims = self.broker.request(phrases, self.timeout, **where)
        if not sims or any(p not in sims for p in phrases):
            result.update(labs=self.with_courses(self.fuse(linked, led, [c['id'] for c in cards]), by_id, linked, led), mode='dictionary')
            return result
        analysis = sims.get(query_key(query)) if understands else None
        if analysis and 'chunk' not in analysis:
            intent, message = REFUSALS.get(analysis.get('intent'), REFUSALS['off_topic'])
            result.update(intent=intent, message=message)
            return result
        if analysis:
            cards = [c for c in self.catalog.search(f"{query['text']} {analysis.get('english') or ''}".strip())
                     if not self.conflicts_with_dislikes(c['id'], dislikes)]
            by_id = {c['id']: c for c in cards}
        ranking, scores, why = self.embedding_ranking(plan_, sims)
        ranking = [lid for lid in ranking if not self.best_is_suspect(lid, why.get(lid))]
        backed = set(ranking[:max(MIN_BACKING, int(len(ranking) * SEMANTIC_BACKING))])
        cards = [c for c in cards if c['strong'] or c['id'] in backed]
        lists = [[c['id'] for c in cards], ranking]
        if analysis:
            usable = set(ranking)
            for name in ('chunk', 'rerank'):
                lists.append(penalized({lid: v for lid, v in analysis[name].items() if lid in usable}, analysis['penalties']))
        fused = self.fuse(linked, led, *lists)
        fused = [lid for lid in fused if not self.conflicts_with_dislikes(lid, dislikes)]
        by_id.update({lid: self.semantic_card(lid, scores[lid], why[lid]) for lid in fused[:TOP_N]
                      if lid not in by_id and lid in scores})
        result['labs'] = self.with_courses(fused, by_id, linked, led)
        result['mode'] = 'embedding'
        return result

    def best_is_suspect(self, lab_id, why):
        """The lab ranks here only because of a paper that likely belongs to a namesake of its professor."""
        topics = self.catalog.profiles[lab_id]['topics']
        return bool(why) and 0 <= why[1] < len(topics) and topics[why[1]].get('suspect', False)

    def semantic_card(self, lab_id, score, why):
        card = super().semantic_card(lab_id, score, why)
        phrase, index = why
        if len(phrase) > QUOTABLE_PHRASE:  # a long phrase is a sentence fragment; quoted back it reads as a mistake
            card['reason'] = card['reason'].replace(f'‘{phrase}’{with_particle(phrase)}', '입력한 관심과', 1)
        topics = self.catalog.profiles[lab_id]['topics']
        if 0 <= index < len(topics):  # pick the sentence of the matched passage that mentions the phrase
            card['evidence'] = [self.catalog._evidence(topics[index], [v for vs in search_terms(phrase).values() for v in vs])]
        return card

    @staticmethod
    def fuse(linked, led, *rankings):
        """When the student asks about a class, its labs count twice in the fusion. Otherwise they come last, so a tie goes to the topic match."""
        rankings = [r for r in rankings if r]
        if linked:
            rankings = [list(linked)] * 2 + rankings if led else rankings + [list(linked)]
        return rrf(*rankings) if len(rankings) > 1 else (rankings[0] if rankings else [])

    def with_courses(self, ids, by_id, linked, led):
        out = []
        for lid in ids[:TOP_N]:
            card = by_id.get(lid)
            if lid in linked and (led or card is None):
                _, course, kind = linked[lid]
                card = self.catalog.course_card(lid, course, kind, card)
            out.append(card)
        return out


# Past MIN_CARDS, labs whose mean liked-phrase score is under this share of the best are dropped: embeddings
# always return something, so a floor keeps unrelated labs off the list. From the RAG eval answers
# (2026-11-02): min 0.76, p10 0.83, median 0.96 of the best score; 0.8 keeps 66 of 69.
MIN_CARDS, RELATIVE_FLOOR = 5, 0.8
# The reranker's probability is well calibrated (50-query review 2026-11-27, one judge): labs under 0.01 were
# unrelated in 54% of cases, labs over 0.5 in 2%. Past MIN_SHOWN cards, a lab under RERANK_FLOOR is not shown, and
# a '관심과 일치' badge needs BADGE_FLOOR (under 0.1 the badged cards averaged grade 1.35 of 3).
RERANK_FLOOR, MIN_SHOWN, BADGE_FLOOR = 0.005, 3, 0.1
# The floor applies only when the reranker found a clear match for this query. For long, many-phrase queries it gives
# every lab a tiny probability (the rocket-engine query: the best lab 0.025, a lab graded 2.6 of 3 at 0.0002), and a
# fixed floor then cut good labs: 80 graded queries, nDCG@10 0.691 -> 0.636 (Kaggle A/B 2026-11-27).
CONFIDENT = 0.3
FEW_RELATED = '입력과 가까운 연구실이 많지 않아 관련도가 높은 곳만 보여 드려요. 다른 표현으로 적으면 더 찾을 수도 있어요.'
# Course labs the search itself did not find: at most this many cards (course-led, otherwise), and outside a
# course-led query their list counts half in the fusion.
COURSE_ONLY_CARDS, COURSE_WEIGHT = (4, 2), 0.5
EVIDENCE_SHOWN, SEARCH_MEMO, QUOTABLE_TEXT = 3, 64, 40
CHUNK_SECTION = {'paper': 'representative_paper', 'intro': 'research_intro', 'profile': 'research_area'}
CHUNK_LABEL = {'paper': '논문', 'intro': '연구소개', 'profile': '연구 분야'}  # a lab summary (R2) is never shown


class RagQueryEngine(CuratedQueryEngine):
    """vectorRAG ranking (engine/modules: retrieve.py, RagQueryEngine) over the worker's chunk scores.

    Per liked phrase (and its R7 rewrite and conditions) every lab gets the weighted sum of its three closest
    chunks, lab summary included (R2); phrase z-scores are averaged, disliked phrases take off their z-score
    above average, professors sharing a homepage fold into one card, and the first rerank_top labs are judged
    again by the cross-encoder (R5). Measured on 128 graded queries (Sonnet grades, 2026-11-26): nDCG@10 0.766
    against 0.622 without the modules.
    """

    def __init__(self, catalog, broker, retriever, reranker=None, rewriter=None, rerank_top=None, timeout=6.0, launcher=None):
        super().__init__(catalog, broker, timeout=timeout, launcher=launcher)
        self.retriever, self.reranker, self.rewriter = retriever, reranker, rewriter
        self.rerank_top = int(rerank_top) if rerank_top else None
        self._memo = OrderedDict()
        self.combiner = lambda values: (values[0] + min(values[1:])) / 2  # [phrase or rewrite z, condition z, ...] -> one z
        # R7 also names a phrase's conditions ('딥러닝', '의학' for '딥러닝 이용한 의학 연구') and a lab must meet each. Off by
        # default (2026-11-26, 128 graded queries): R7 split 97 of them, and requiring every condition lowered
        # nDCG@10 in the first pass (weakest condition only -0.122; tiers 'all conditions then any' -0.052), while
        # not splitting gave +0.040 [+0.015, +0.066] in the first pass and +0.013 [+0.001, +0.026] with the reranker.
        self.split_conditions = False
        self.always_summary = True  # the reranker reads every lab's summary, not only when it is among the lab's closest chunks
        self.rerank_english = False  # also give the reranker the R7 English rewrite (the earlier engine did; measured 2026-11-26)

    def search(self, text, allow_remote=True, rewrite=True):
        """rewrite=False: no new R7 rewrite (a client over its hourly limit); rewrites already made are still used."""
        parsed = classify_curated_query(text)
        if parsed['intent'] != 'search' or self.broker is None:
            return super().search(text, allow_remote)
        if allow_remote and self.launcher and not self.broker.available():
            return super().search(text, allow_remote)  # starts the worker and answers from the dictionary meanwhile
        from .rag.remote import Unavailable
        try:
            return self.rag_search({**parsed, 'raw': text}, allow_remote, rewrite)
        except Unavailable:
            return super().search(text, allow_remote=False)

    def rag_search(self, parsed, remote, rewrite=True):
        norm, likes, dislikes = parsed['norm'], parsed['likes'], parsed['dislikes']
        result = {'labs': [], 'intent': 'search', 'mode': 'embedding', 'message': parsed['message'],
                  'interpretation': {'likes': likes, 'dislikes': dislikes}, 'uncertain': parsed['uncertain'], 'reasons': []}
        cue = bool(COURSE_CUE.search(norm))
        courses = self.catalog.courses_named(likes, cue)
        linked = {lid: link for lid, link in self.catalog.course_labs(courses).items()
                  if not self.conflicts_with_dislikes(lid, dislikes)}
        # Course-led only when every liked phrase names a class: a topic that merely shares a title
        # ('컴퓨터 구조와 시스템 보안') or a class mentioned beside other interests leaves the search in front.
        led = bool(linked) and all(self.catalog.courses_named([p], cue) for p in likes)
        if courses:
            result['courses'] = [{'code': c['code'], 'name': c['title']} for c, _ in courses]
        # The worker's refusal check (N1, GATE_MARGIN), skipped like in CuratedQueryEngine when a dislike was read
        gate = None if dislikes or (AVOID_CUE.search(norm) and INTEREST_CLAUSE.search(norm)) or linked else (parsed['raw'], GATE_MARGIN)
        from .rag.remote import Refused
        try:
            # Course labs are judged by the reranker too, so the floor and the dislikes apply to them as well.
            ranking, cards, judged = self.ranked(likes or [norm], dislikes, remote, gate, rewrite, extra=tuple(linked))
        except Refused as refusal:
            intent, message = REFUSALS.get(refusal.args[0], REFUSALS['off_topic'])
            result.update(intent=intent, message=message, mode='embedding')
            return result
        confident = bool(judged) and max(judged.values()) >= CONFIDENT
        if confident:
            linked = {lid: link for lid, link in linked.items() if lid in cards or judged.get(lid, 0.0) >= RERANK_FLOOR}
        course_only = [lid for lid in self.rag_fuse(linked, led, []) if lid not in cards][:COURSE_ONLY_CARDS[0 if led else 1]]
        linked = {lid: link for lid, link in linked.items() if lid in cards or lid in course_only}
        fused = [lid for lid in self.rag_fuse(linked, led, ranking) if not self.conflicts_with_dislikes(lid, dislikes)]
        out = []
        for lid in fused[:TOP_N]:
            card = cards.get(lid)
            if lid in linked and (led or card is None):
                _, course, kind = linked[lid]
                card = self.catalog.course_card(lid, course, kind, card)
                if lid in judged:
                    card['rerank'] = round(judged[lid], 4)
            if card is not None:
                out.append(card)
        result['labs'] = out
        if confident and len(out) < TOP_N and any(v < RERANK_FLOOR for v in judged.values()):
            result['message'] = FEW_RELATED
        return result

    def group(self, phrase, remote):
        """([phrase, its English rewrite (R7)], [its conditions]) for one liked phrase."""
        if self.rewriter is None:
            return [phrase], []
        out = self.rewriter(phrase, remote=remote)
        leads = [phrase] + ([out['english']] if out.get('english') and out['english'] != phrase else [])
        if not self.split_conditions:
            return leads, []
        return leads, [f for f in out.get('facets', []) if f not in leads]

    def ranked(self, likes, dislikes, remote=True, gate=None, rewrite=True, extra=()):
        """(lab ids best first, {lab id: card}, {lab id: reranker probability}) for the liked and disliked phrases;
        memoized per phrase set. extra: labs the reranker judges even outside the first candidates (course labs)."""
        # The phrases as written go first, with the worker's refusal check: an off-topic query costs no rewrite.
        found = self.retriever.lab_scores(list(likes) + list(dislikes), remote=remote, gate=gate)
        groups = [self.group(p, remote and rewrite) for p in likes]
        key = (tuple(likes), tuple(dislikes), repr(groups), gate, tuple(extra))
        if key in self._memo:
            self._memo.move_to_end(key)
            return self._memo[key]
        more = [p for leads, facets in groups for p in leads + facets if p not in found]
        if more:
            found = {**found, **self.retriever.lab_scores(more, remote=remote)}
        # A lab must meet every condition of a phrase: the group value is the mean of the phrase's (or its
        # rewrite's, whichever matches the lab better) and the weakest condition's (AND).
        labs = [lid for lid in found[likes[0]] if lid in self.catalog.profiles]
        if not labs:
            return [], {}, {}
        score = lambda p, lid: found[p].get(lid, (0.0, []))[0]
        both = lambda values: values[0] if len(values) == 1 else (values[0] + min(values[1:])) / 2
        combine = lambda values: values[0] if len(values) == 1 else self.combiner(values)
        raw = {lid: sum(both([max(score(p, lid) for p in leads)] + [score(f, lid) for f in facets]) for leads, facets in groups) / len(groups)
               for lid in labs}
        columns = []
        for leads, facets in groups:
            lead = [zscores([score(p, lid) for lid in labs]) for p in leads]
            member = [[max(col[n] for col in lead) for n in range(len(labs))]] + [zscores([score(f, lid) for lid in labs]) for f in facets]
            columns.append([combine([col[n] for col in member]) for n in range(len(labs))])
        mean_z = {lid: sum(col[n] for col in columns) / len(columns) for n, lid in enumerate(labs)}
        penalties = [{lid: score(p, lid) for lid in labs} for p in dislikes]
        chunks = {lid: [e for leads, facets in groups for p in leads + facets for e in found[p].get(lid, (0.0, []))[1]] for lid in labs}
        # Professors sharing a lab homepage (meta.group) are one card at the best member's rank (D2).
        ranking, members = self.fold(penalized(mean_z, penalties, raw), chunks)
        english = [leads[1] for leads, _ in groups if len(leads) > 1] if self.rerank_english else []
        judged = self.rerank(likes, dislikes, ranking, members, chunks, remote, english, extra) if self.reranker else {}
        if judged:
            ranking = sorted((lid for lid in judged if lid in ranking), key=lambda lid: -judged[lid]) + [lid for lid in ranking if lid not in judged]
        best = max(raw.values())
        kept = [lid for n, lid in enumerate(ranking) if n < MIN_CARDS or raw[lid] >= best * RELATIVE_FLOOR][:TOP_N]
        if judged and max(judged.values()) >= CONFIDENT:
            kept = [lid for n, lid in enumerate(kept) if n < MIN_SHOWN or judged.get(lid, 0.0) >= RERANK_FLOOR]
        variants = [v for vs in search_terms(' '.join(likes)).values() for v in vs]
        # {chunk id: best score for any disliked phrase}, per lab: such a chunk is no evidence for the likes.
        avoided = {lid: {c['id']: s for p in dislikes for m in members[lid] for s, c in found[p].get(m, (0.0, []))[1]} for lid in kept}
        cards = {lid: self.rag_card(lid, raw[lid], [e for m in members[lid] for e in chunks[m]], variants, avoided[lid]) for lid in kept}
        for lid in kept:
            if lid in judged:
                cards[lid]['rerank'] = round(judged[lid], 4)
                if judged[lid] < BADGE_FLOOR:
                    cards[lid]['matched_topics'] = []
        if judged or not self.reranker:  # a first pass the reranker missed is not kept: the next search tries again
            self._memo[key] = (kept, cards, judged)
            if len(self._memo) > SEARCH_MEMO:
                self._memo.popitem(last=False)
        return kept, cards, judged

    def rerank(self, likes, dislikes, ranking, members, chunks, remote, english=(), extra=()):
        """{lab id: cross-encoder probability, discounted by how surely the lab is about a disliked subject} for the
        first candidates and `extra` (R5); {} when the worker does not answer (the first-pass order stays).
        The reranker also reads the dislikes as a query of their own: '웻랩은 싫고', '동물실험은 꺼려져' are about how a
        lab works, which a similarity penalty on the first pass cannot see."""
        from .rag import rerank
        from .rag.remote import Unavailable
        top = ranking[:self.rerank_top or rerank.TOP]
        top += [lid for lid in dict.fromkeys(extra) if lid in members and lid not in top]
        summary = self.summaries() if self.always_summary else {}
        docs = [rerank.passage(self.catalog.profiles[lid], [e for m in members[lid] for e in chunks[m]], summary=summary.get(lid)) for lid in top]
        try:
            probs = self.reranker.score(rerank.query([*likes, *english]), docs, likes, remote=remote)
            avoid = self.reranker.score(rerank.query(dislikes), docs, likes, remote=remote) if dislikes else [0.0] * len(top)
        except Unavailable:
            return {}
        return {lid: p * (1 - rerank.DISLIKE * a) for lid, p, a in zip(top, probs, avoid)}

    def summaries(self):
        """{lab id: its summary chunk (R2)}, from the chunk file the retriever loaded."""
        if getattr(self, '_summaries', None) is None:
            self._summaries = {c['owner']: c for c in getattr(self.retriever, 'chunks', {}).values() if c.get('kind') == 'summary'}
        return self._summaries

    @staticmethod
    def fold(ranking, chunks):
        """(ranking with one id per lab group, {kept id: [member ids, best first]})."""
        order, members, seen = [], {}, {}
        for lid in ranking:
            group = next((c['meta'].get('group') for _, c in chunks.get(lid, []) if c.get('meta', {}).get('group')), None) or lid
            if group in seen:
                members[seen[group]].append(lid)
                continue
            seen[group] = lid
            members[lid] = [lid]
            order.append(lid)
        return order, members

    @staticmethod
    def rag_fuse(linked, led, ranking):
        """Course labs (best link first) count twice when the student asks only about classes, otherwise half."""
        if not linked:
            return ranking
        courses = sorted(linked, key=lambda lid: -linked[lid][0])
        weight = {lid: 0.0 for lid in [*ranking, *courses]}
        for i, lid in enumerate(ranking):
            weight[lid] += 1 / (RRF_K + i + 1)
        for i, lid in enumerate(courses):
            weight[lid] += (2 if led else COURSE_WEIGHT) / (RRF_K + i + 1)
        return sorted(weight, key=lambda lid: -weight[lid])

    def rag_card(self, lab_id, score, chunks, variants, avoided=None):
        """avoided: {chunk id: score for a disliked phrase}; a chunk at least that close to a dislike is dropped."""
        card = self.catalog.card(lab_id)
        avoided = avoided or {}
        best = {}
        for s, chunk in chunks:  # one chunk may match several liked phrases; keep its best score
            if chunk['id'] not in best or s > best[chunk['id']][0]:
                best[chunk['id']] = (s, chunk)
        ordered = [c for s, c in sorted(best.values(), key=lambda x: -x[0])
                   if c['kind'] in CHUNK_LABEL and avoided.get(c['id'], float('-inf')) < s]
        # The profile chunk only repeats names and areas; a few intro chunks are page furniture ('Read more...').
        shown = ([c for c in ordered if c['kind'] != 'profile' and len(c['text'].strip()) >= QUOTABLE_TEXT] or ordered)[:EVIDENCE_SHOWN]
        evidence = [self.chunk_evidence(lab_id, c, variants) for c in shown]
        # '관심과 일치' marks only the areas the quoted chunks sit under, not any chunk among the closest few per phrase.
        headings = {(c['meta'].get('heading') or '').strip().lower() for c in shown}
        kinds = [CHUNK_LABEL[c['kind']] for c in ordered]
        counts = ', '.join(f'{k} {kinds.count(k)}개' for k in dict.fromkeys(kinds))
        card.update(matched_topics=[t['id'] for t in card['topics'] if t['label'].strip().lower() in headings],
                    evidence=evidence, score=round(score, 3), connection='semantic',
                    reason=f'입력한 관심과 의미가 가까운 {counts}를 연구실 자료에서 찾았어요.' if counts else '입력한 관심과 의미가 가까운 내용을 연구실 자료에서 찾았어요.')
        if card['status'] == 'thin':
            card['reason'] += ' 수집 자료가 제목 수준이라 연구 내용은 홈페이지에서 확인이 필요합니다.'
        return card

    def chunk_evidence(self, lab_id, chunk, variants=()):
        """A matched chunk in the card evidence format (CuratedCatalog._evidence)."""
        kind, meta, text = chunk['kind'], chunk['meta'], chunk['text']
        profile = self.catalog.profiles[lab_id]
        section, year = CHUNK_SECTION[kind], None
        if kind == 'paper':
            title, _, body = text.partition('\n')
            urls, year = ([f"https://doi.org/{meta['doi']}"] if meta.get('doi') else []), meta.get('year')
        elif kind == 'intro':
            title, body = (meta.get('heading') or '').strip(), text
            urls = next((t['source_urls'] for t in profile['topics'] if t['section'] == 'research_intro' and t.get('source_urls')), [profile['lab_url']])
            if title:
                section = 'intro'  # cards show the heading of an intro part; 'research_intro' would hide it
        else:
            title, body, urls = text.split('\n')[-1], '', [profile['lab_url']]
        shown, marks = snippet(body, variants) if body.strip() else ('', [])
        return {'topic': meta.get('heading') or kind, 'label': title or EVIDENCE_KIND[CHUNK_SECTION[kind]], 'text': text,
                'urls': safe_urls(urls)[:1], 'section': section, 'role': 'domain', 'kind': EVIDENCE_KIND[CHUNK_SECTION[kind]],
                'title': clip(title, 200), 'snippet': shown, 'marks': marks, 'full': body.strip() if body.strip() and body.strip() != shown else '',
                'year': year, 'chunk_id': chunk['id']}
