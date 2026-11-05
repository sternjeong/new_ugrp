"""Positive/negative query interpretation over the new curated catalog."""
import re

from .curated_catalog import COURSE_CUE, COURSE_WORD
from .query_engine import QueryEngine, broad_only, interpret, is_nonsense, normalize, rrf, TOP_N


PROCEDURE = re.compile(r'(수강\s*신청|대학원\s*(?:지원|입학|진학)|교수(?:님)?께?\s*(?:메일|이메일)|(?:지원|신청|컨택|면접|장학금|추천서).*(?:방법|어떻게|절차))')
PROCEDURE_QUESTION = re.compile(r'(어떻게|방법|절차|알려|해야|하나요|할까요|쓰나요)')
NEGATIVE_CUE = re.compile(r'(싫|별로|관심\s*없|좋아하지\s*않|흥미\s*없|재미없|빼고|제외|말고|보다)')
KEYBOARD_NOISE = re.compile(r'^(?:asdf|qwer|zxcv|ㅋㅋ+|ㅎㅎ+|ㅠㅠ+|ㅜㅜ+)$', re.I)


def classify_curated_query(text):
    """Decide whether a query may reach retrieval, independent of catalog matches."""
    norm = normalize(text)
    normalized_negative = re.sub(r'좋아하지\s*않(?:지만|아요|습니다|아)', '싫고', norm)
    parsed = interpret(normalized_negative)
    likes, dislikes = parsed['likes'], parsed['dislikes']
    # '컴퓨터구조 수업' → '컴퓨터구조': the word 수업 alone pulls labs about learning and attention.
    likes = list(dict.fromkeys(re.sub(r'\s+', ' ', COURSE_WORD.sub(' ', p)).strip() or p for p in likes))
    result = {'norm': norm, 'likes': likes, 'dislikes': dislikes,
              'intent': 'search', 'message': None, 'uncertain': False}
    if is_nonsense(norm) or KEYBOARD_NOISE.fullmatch(norm):
        result.update(intent='nonsense', likes=[], dislikes=[],
                      message='관심 있는 연구 주제나 문제를 적어 주세요.')
    elif PROCEDURE.search(norm) and PROCEDURE_QUESTION.search(norm):
        result.update(intent='career', message='연구실 추천을 위한 관심 분야나 연구 문제를 적어 주세요.')
    elif not likes and dislikes:
        result.update(intent='need_likes', message='궁금한 연구 주제도 함께 적어 주세요.')
    elif broad_only(likes):
        result.update(intent='too_broad', message='조금 더 구체적인 연구 주제나 문제를 적어 주세요.')
    elif NEGATIVE_CUE.search(norm) and not dislikes:
        result.update(intent='need_clarification', uncertain=True,
                      message='피하고 싶은 주제를 정확히 이해하지 못했어요. 좋아하는 주제와 피하고 싶은 주제를 나눠 적어 주세요.')
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

    def search(self, text):
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
        if self.launcher and self.broker and not self.broker.available() and self.launcher.ensure_started():
            result.update(labs=self.with_courses(self.fuse(linked, led, [c['id'] for c in cards]), by_id, linked, led),
                          mode='starting', message='의미 검색을 준비하고 있어요. 잠시만 기다려 주세요.')
            return result
        phrases = list(dict.fromkeys((likes or [norm]) + dislikes + [norm]))
        sims = self.broker.request(phrases, self.timeout) if self.broker else None
        if not sims or any(p not in sims for p in phrases):
            result.update(labs=self.with_courses(self.fuse(linked, led, [c['id'] for c in cards]), by_id, linked, led), mode='dictionary')
            return result
        ranking, scores, why = self.embedding_ranking(plan_, sims)
        fused = self.fuse(linked, led, [c['id'] for c in cards], ranking)
        fused = [lid for lid in fused if not self.conflicts_with_dislikes(lid, dislikes)]
        by_id.update({lid: self.semantic_card(lid, scores[lid], why[lid]) for lid in fused[:TOP_N] if lid not in by_id})
        result['labs'] = self.with_courses(fused, by_id, linked, led)
        result['mode'] = 'embedding'
        return result

    @staticmethod
    def fuse(linked, led, *rankings):
        """When the student asks about a class, its labs count twice in the fusion."""
        rankings = [r for r in rankings if r]
        if linked:
            rankings = [list(linked)] * (2 if led else 1) + rankings
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
