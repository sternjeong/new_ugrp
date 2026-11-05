"""Positive/negative query interpretation over the new curated catalog."""
import re

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
        if self.launcher and self.broker and not self.broker.available() and self.launcher.ensure_started():
            result.update(labs=cards[:TOP_N], mode='starting',
                          message='의미 검색을 준비하고 있어요. 잠시만 기다려 주세요.')
            return result
        phrases = list(dict.fromkeys((likes or [norm]) + dislikes + [norm]))
        sims = self.broker.request(phrases, self.timeout) if self.broker else None
        if not sims or any(p not in sims for p in phrases):
            result.update(labs=cards[:TOP_N], mode='dictionary')
            return result
        ranking, scores, why = self.embedding_ranking(plan_, sims)
        fused = rrf([c['id'] for c in cards], ranking) if cards else ranking
        fused = [lid for lid in fused if not self.conflicts_with_dislikes(lid, dislikes)]
        result['labs'] = [by_id[lid] if lid in by_id else self.semantic_card(lid, scores[lid], why[lid])
                          for lid in fused[:TOP_N]]
        result['mode'] = 'embedding'
        return result
