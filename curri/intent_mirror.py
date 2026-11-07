"""Read-only 'what I understood' mirror for long free-text interests.

Rule based, no model call. Every slot value is a verbatim substring of the student's text and
carries the sentence it came from. It never judges who the student is, never fills a dimension the
student did not mention, and does not change search ranking or storage (docs/product/INTENT_MIRROR_SPEC.md).
"""
import re

MIN_CHARS = 40
MIN_DIMENSIONS = 2
QUOTE_LIMIT = 100
TOPIC_LIMIT = 30

# (key, label, pattern). Keywords only name a dimension; they do not score labs.
DIMENSIONS = (
    ('style', '하고 싶은 방식', re.compile(
        r'바이브\s*코딩|파이썬|(?<![A-Za-z])python(?![A-Za-z])|프레임워크|(?<![A-Za-z])framework(?![A-Za-z])|'
        r'기획|설계|직접\s*(?:만들|구현)|빠르게\s*만들|프로토타입|이론|증명|실험', re.I)),
    ('output', '만들고 싶은 결과', re.compile(
        r'데모|논문|창업|특허|(?<![A-Za-z])IP(?![A-Za-z])|제품|서비스|포트폴리오', re.I)),
    ('constraint', '환경·조건', re.compile(
        r'인턴|풀타임|\d+\s*개월|방학|자율|지도\s*(?:방식|스타일)|피드백|부담|요구\s*사항|개발\s*환경|공개\s*정책')),
)
LABELS = {'topic': '관심 주제', **{key: label for key, label, _ in DIMENSIONS}}


def sentences(text):
    """(start, end) spans of sentences, in the student's own text."""
    spans, start = [], 0
    for m in re.finditer(r'[.!?。]+\s+|\n+', text):
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def quote_around(text, span, hit):
    """Sentence containing the hit, cut on whitespace to QUOTE_LIMIT; always a slice of text."""
    a, b = span
    if b - a > QUOTE_LIMIT:
        a = max(a, hit.start() - QUOTE_LIMIT // 3)
        b = min(b, a + QUOTE_LIMIT)
        while a > span[0] and not text[a - 1].isspace():
            a += 1
        while b < span[1] and not text[b].isspace():
            b -= 1
    return text[a:b].strip()


def build_mirror(text, likes=(), dislikes=()):
    """Return {'slots': [...], 'missing': [...]} or None when the text does not say enough.

    Shown only when at least two dimensions were named and the text is long enough; length alone
    is not a trigger because a long text can repeat one thing.
    """
    text = (text or '').strip()
    if len(text) < MIN_CHARS:
        return None
    spans = sentences(text)
    slots = []
    # The query interpreter can return a whole sentence tail for long text; that is not a topic name.
    # A phrase that names a way of working, an output or a condition belongs to those dimensions, not to the topic.
    likes = [like for like in likes if len(like) <= TOPIC_LIMIT and not any(pattern.search(like) for _, _, pattern in DIMENSIONS)]
    if likes:
        topic_quote = ''
        for like in likes:
            at = text.find(like)
            if at >= 0:
                span = next(s for s in spans if s[0] <= at < s[1])
                topic_quote = quote_around(text, span, re.search(re.escape(like), text))
                break
        slots.append({'key': 'topic', 'label': LABELS['topic'], 'values': list(likes), 'quote': topic_quote})
    for key, label, pattern in DIMENSIONS:
        hits = list(pattern.finditer(text))
        if not hits:
            continue
        values = list(dict.fromkeys(h.group(0).strip() for h in hits))
        first = hits[0]
        span = next(s for s in spans if s[0] <= first.start() < s[1])
        slots.append({'key': key, 'label': label, 'values': values, 'quote': quote_around(text, span, first)})
    if len(slots) < MIN_DIMENSIONS:
        return None
    named = {slot['key'] for slot in slots}
    missing = [LABELS[key] for key, _, _ in DIMENSIONS if key not in named]
    return {'slots': slots, 'avoid': list(dislikes), 'missing': missing}


MAX_VALUE_CHARS = 40
MAX_VALUES = 8


def clean_slots(raw):
    """Validate what the student confirmed. The student may edit freely, so values are not
    required to appear in the original text; they are marked as the student's own words."""
    if not isinstance(raw, list) or len(raw) > len(LABELS):
        raise ValueError('정리한 내용 형식이 올바르지 않아요.')
    cleaned, seen = [], set()
    for slot in raw:
        key = slot.get('key') if isinstance(slot, dict) else None
        values = slot.get('values') if isinstance(slot, dict) else None
        if key not in LABELS or key in seen or not isinstance(values, list) or len(values) > MAX_VALUES:
            raise ValueError('정리한 내용 형식이 올바르지 않아요.')
        seen.add(key)
        kept = []
        for value in values:
            if not isinstance(value, str):
                raise ValueError('정리한 내용 형식이 올바르지 않아요.')
            value = re.sub(r'\s+', ' ', value).strip()
            if len(value) > MAX_VALUE_CHARS:
                raise ValueError(f'각 항목은 {MAX_VALUE_CHARS}자 이하로 적어 주세요.')
            if value and value not in kept:
                kept.append(value)
        if kept:
            cleaned.append({'key': key, 'label': LABELS[key], 'values': kept})
    return cleaned
