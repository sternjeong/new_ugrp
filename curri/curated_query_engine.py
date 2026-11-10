"""Positive/negative query interpretation over the new curated catalog."""
import re

from .curated_catalog import COURSE_CUE, COURSE_WORD, search_terms
from .embed_broker import query_key
from .query_engine import LAMBDA, QueryEngine, broad_only, interpret, is_nonsense, normalize, rrf, TOP_N, with_particle, zscores


PROCEDURE = re.compile(r'(수강\s*신청|대학원\s*(?:지원|입학|진학)|교수(?:님)?께?\s*(?:메일|이메일)|(?:지원|신청|컨택|면접|장학금|추천서).*(?:방법|어떻게|절차))')
PROCEDURE_QUESTION = re.compile(r'(어떻게|방법|절차|알려|해야|하나요|할까요|쓰나요)')
NEGATIVE_CUE = re.compile(r'(싫|별로|관심\s*없|좋아하지\s*않|흥미\s*없|재미없|빼고|제외|말고|보다)')
CLAUSE_BREAK = re.compile(r'(?<=[.!?])\s+|\n+|(?<=싶고),\s*|(?<=좋고),\s*')
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


def penalized(scores, penalties):
    """Labs by z-scored score, minus the z-score of each disliked subject where it is above average."""
    labs = list(scores)
    if not labs:
        return []
    total = dict(zip(labs, zscores([scores[lid] for lid in labs])))
    for penalty in penalties:
        z = dict(zip(labs, zscores([penalty.get(lid, 0.0) for lid in labs])))
        total = {lid: value - LAMBDA * max(0.0, z[lid]) for lid, value in total.items()}
    return sorted(labs, key=lambda lid: -total[lid])


def classify_curated_query(text):
    """Decide whether a query may reach retrieval, independent of catalog matches."""
    norm = normalize(text)
    normalized_negative = re.sub(r'좋아하지\s*않(?:지만|아요|습니다|아)', '싫고', norm)
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
    elif not likes and dislikes:
        result.update(intent='need_likes', message='궁금한 연구 주제도 함께 적어 주세요.')
    elif AVOID_ONLY.search(norm) and not HAS_POSITIVE.search(norm):
        result.update(intent='need_likes', message='궁금한 연구 주제도 함께 적어 주세요.')
    elif broad_only(likes):
        result.update(intent='too_broad', message='조금 더 구체적인 연구 주제나 문제를 적어 주세요.')
    elif NEGATIVE_CUE.search(norm) and not dislikes:
        result.update(intent='need_clarification', uncertain=True,
                      message='피하고 싶은 주제를 정확히 이해하지 못했어요. 좋아하는 주제와 피하고 싶은 주제를 나눠 적어 주세요.')
    result['likes'] = list(dict.fromkeys(clean_like(p) for p in result['likes']))
    return result


class CuratedQueryEngine(QueryEngine):
    def conflicts_with_dislikes(self, lab_id, dislikes):
        """Only reject explicit topic-label overlaps; do not infer hidden semantics."""
        labels = [topic['label_ko'].lower() for topic in self.catalog.profiles[lab_id]['topics']]
        return any(phrase.lower() in label for phrase in dislikes for label in labels)

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
        # Course-led only when the student talks about a class, not when a topic merely shares a title
        # ('컴퓨터 구조와 시스템 보안' must still find security labs).
        led = bool(linked) and (cue or all(self.catalog.courses_named([p], cue) for p in likes))
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
