"""관심 문장 → {likes, dislikes} 규칙 해석 (표준 라이브러리만 사용).
1) '싫다·별로·관심 없다·질렸다·빼고' 앞의 구절을 싫은 쪽으로 떼어 낸다.
2) 'A보다(는) B', 'A 말고 B'는 A를 싫은 쪽, B를 좋은 쪽으로 본다.
3) 남은 문장에서 어미(하고 싶어요·궁금해요 등)를 지우고 '과·와·랑·이랑·이나·나'로 구절을 나눈다. 구절 안의 공백은 유지한다."""
import re

NEG = r'(?P<neg>.+?)\s*(?:은|는|이|가)?\s*(?:싫(?:은데|고|어서?)|별로(?:고|인데)?|관심\s*없(?:고|는데)?|질렸(?:고|는데)|질려서?|어렵(?:고|지만)|어려워서?|빼고|제외하고)\s*'
TAIL = re.compile(r'(?:\S*고\s*싶\S*|(?:은|는|이|가)?\s*좋아\S*|(?:을|를)?\s*(?:하고|해보고|해\s*보고|공부하고|연구하고|알고|알아보고|만들고|배우고)\s*싶\S*|에?\s*(?:도\s*)?관심\s*(?:이\s*)?(?:있|많)\S*|(?:이|가)\s*(?:궁금|재밌|재미있|좋|더\s*끌려|끌려)\S*|(?:을|를)?\s*(?:합친|같이|함께)\s*(?:연구)?(?:를)?|둘\s*다|(?:이|가)?\s*더\s*좋\S*|(?:이|가)\s*궁금\S*)')
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
        return {'likes': _phrases(m.group('b')), 'dislikes': _phrases(m.group('a'))}
    dislikes = []
    def grab(mm):
        dislikes.extend(_phrases(mm.group('neg')))
        return ' '
    rest = re.sub(NEG, grab, t)
    return {'likes': _phrases(rest), 'dislikes': dislikes}

if __name__ == '__main__':
    import json
    for q in json.load(open('queries.json', encoding='utf-8')):
        print(q['id'], q['text'], '->', interpret(q['text']))
