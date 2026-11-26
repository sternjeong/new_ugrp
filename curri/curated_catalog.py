"""Service catalog backed only by reviewed sunwoo labs, courses and papers."""
import hashlib
import json
import math
import re
from pathlib import Path

from .catalog import safe_urls
from .text_cleanup import tidy


def load_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


GENERIC_AREA_LABELS = {'research overview', 'research interests', 'research areas'}
# Words that only restate "<professor> (교수) 연구실" and add no name of the lab itself.
LAB_NAME_FILLER = re.compile(r'교수님|교수|연구실|연구팀|실험실|laboratory|lab|research\s*group|group|[\W_]', re.I)


# Search helpers. Much of the lab material is English, so common Korean research terms also look for
# their English names. Prefixes ("organic chem") match inside longer words, like the Korean substrings.
SEARCH_STOPWORDS = {'연구', '관심', '분야', '공부', '하고', '싶어요', '싶다', '싶은', '좋아요', '궁금', '재밌', '수업', 'study', 'research', 'want', 'the', 'and',
                    # Words that frame a question rather than name a topic. Most lab material is English, so these look rare and would count heavily.
                    '영향', '미치', '미치는', '효과', '관계', '방법', '방안', '문제', '사용', '활용', '이용', '결과', '변화', '과정', '역할', '특성', '원인', '현상',
                    '기술', '개발', '분석', '설계', '시스템', '응용', '기반', '관련', '대한', '위한', '통한', '좋아', '것을', '어떤', '어떻게', '알고', '주는', '연구하고', '연구하는', '연구할', '연구해'}
PARTICLE = re.compile(r'(?:으로|에서|이랑|에게|처럼|까지|부터|을|를|은|는|이|가|와|과|의|에|로|도|만|랑)$')
EXPANSIONS = {
    '자율주행': ['autonomous driving', 'self-driving', 'autonomous vehicle'], '자연어처리': ['natural language', '자연어'],
    '자연어': ['natural language'], '언어모델': ['language model', 'llm'], '드론': ['drone', 'uav', 'unmanned aerial'],
    '유기화학': ['organic chem', 'organic synthesis', '유기합성'], '뇌과학': ['neuroscience', 'brain', '신경과학'],
    '로봇': ['robot'], '강화학습': ['reinforcement learning'], '컴퓨터비전': ['computer vision', 'image recognition'],
    '딥러닝': ['deep learning'], '머신러닝': ['machine learning', '기계학습'], '반도체': ['semiconductor'],
    '배터리': ['battery', 'batteries', '이차전지'], '전해질': ['electrolyte'], '단백질': ['protein'], '신약': ['drug discovery', 'drug design'],
    '양자컴퓨터': ['quantum comput', 'qubit', '양자 컴퓨'], '양자': ['quantum'], '태양전지': ['solar cell', 'photovoltaic'],
    '페로브스카이트': ['perovskite'], '웨어러블': ['wearable'], '센서': ['sensor'], '그래핀': ['graphene'], '보안': ['security'],
    '블록체인': ['blockchain'], '금융': ['financ'], '핵융합': ['fusion', 'tokamak'], '수소': ['hydrogen'], '연료전지': ['fuel cell'],
    '촉매': ['catalys'], '유전자': ['genom', 'genetic', 'crispr', 'gene editing'], '추천': ['recommend'], '그래픽스': ['graphics', 'rendering'],
    '디스플레이': ['display'], '최적화': ['optimiz'], '통계': ['statistic'], '가상현실': ['virtual reality', 'metaverse'],
    '메타버스': ['metaverse', 'virtual reality', '가상현실'], '탄소포집': ['carbon capture', 'co2 capture'], '기후': ['climate'],
    '암': ['cancer', 'tumor', '항암', '종양', '암세포'], '면역': ['immun'], '의료영상': ['medical imag'], '나노': ['nano'],
    '잠': ['sleep', '수면'], '수면': ['sleep'], '뇌': ['brain', 'neuro', '뇌과학', '신경'],
}
COMMON_FRACTION = 0.25  # a word found in more labs than this says little on its own
COURSE_CUE = re.compile(r'수업|과목|강의|수강')
COURSE_WORD = re.compile(r'(?:수업|과목|강의|수강)\S*')
COURSE_LIMIT = 8
COURSE_LAB_LIMIT = 10
TEACHER_BASE = 0.55   # instructors whose lab has no similarity entry for the course (top 20 per lab only)
TEACHER_BONUS = 0.15  # teaching the course is direct evidence; similarity alone is an estimate
EXACT_BONUS = 0.1     # the course the student named outranks longer titles that merely contain it
COURSE_ALIASES = {'선대': '선형대수', '일물': '일반물리', '컴구': '컴퓨터구조',
                  '운체': '운영체제', '자료구조': '데이터구조'}
SIMILAR_RATIO = 0.95  # relative to the best stored similarity for this course
DEPARTMENT_BONUS = 0.08


def course_base(title):
    """'유기화학I' → 유기화학, '일반물리: 역학과 파동' → 일반물리, '일반물리(H): …' → 일반물리."""
    base = re.split(r'[:(（]', title)[0]
    base = re.sub(r'\s+', '', base)
    return re.sub(r'(?:I{1,3}|IV|Ⅰ|Ⅱ|Ⅲ|\d+)$', '', base)


def search_terms(text):
    """Query words without particles, each with its English/spacing variants (all lowercase, spaces removed)."""
    words = []
    for raw in re.findall(r'[가-힣]+|[A-Za-z][A-Za-z0-9-]*', text):
        word = raw.lower()
        if re.fullmatch(r'[가-힣]+', word) and len(word) > 2:
            word = PARTICLE.sub('', word) if len(PARTICLE.sub('', word)) >= 2 else word
        elif PARTICLE.sub('', word) in EXPANSIONS:  # 잠이 → 잠, 암을 → 암: short words keep theirs unless the stem is a known term
            word = PARTICLE.sub('', word)
        if word in SEARCH_STOPWORDS or (re.fullmatch(r'[가-힣]+', word) and len(word) < 2 and word not in EXPANSIONS) or (word.isascii() and len(word) < 3):
            continue
        words.append(word)
    # Adjacent Korean words may form one known term ("컴퓨터 비전" → 컴퓨터비전, "언어 모델" → 언어모델).
    joined = [a + b for a, b in zip(words, words[1:]) if a + b in EXPANSIONS]
    terms = {}
    for word in dict.fromkeys(joined + words):
        # A one-letter Korean word (암) would match inside unrelated words, so only its variants are searched.
        variants = ([] if len(word) < 2 else [word]) + EXPANSIONS.get(word, [])
        terms[word] = [v.replace(' ', '').lower() for v in variants]
    for whole in joined:  # the parts of a recognised compound are not searched separately
        for part in list(terms):
            if part != whole and part in whole and part not in EXPANSIONS:
                terms.pop(part)
    return terms


def area_label(text):
    return str(text or '').strip().strip('.,;:').strip()


EVIDENCE_KIND = {'representative_paper': '대표 논문', 'research_area': '연구 분야', 'research_intro': '연구실 소개',
                 'course': '과목 설명'}
SENTENCE_BREAK = re.compile(r'(?<=[.!?])\s+(?=[A-Z가-힣0-9(“"\'])|\n+')
SNIPPET_LIMIT = 600
READABLE_SENTENCE = 40
COURSE_PREFIX = re.compile(r'^(?:특강|특론)\s*[:：]\s*')
ABBREVIATION_END = re.compile(r'(?:\b(?:Prof|Dr|Mr|Ms|Mrs|Ph|Dept|Univ|vs|etc|al|No|Fig|Inc|Lab)|\be\.g|\bi\.e|Ph\.D)\.$')
OPEN_ENDED = re.compile(r'\b(?:to|for|of|at|in|on|by|with|and|or|the|a|an|are|is|from|that|which|can|as)$', re.I)
NOT_RESEARCH = re.compile(r'(?:@\w|\bat postech dot\b|https?:|\bTel\b|\bE-?mail\b|Click\b|Image by|Welcome (?:to|Message)|feel free|contact (?:me|us)|Positions? available|looking for|seeking prospective|recruit|postdoc|모집|이메일|\bOffice|Resume|Portfolio|listed on this page|regular updates|preprint posted|교수\]|\bHome\b|\bKeywords?\s*-)', re.I)
CAREER_LINE = re.compile(r'^\W*(?:(?:19|20)\d\d\b|In (?:19|20)\d\d\b|\d\d\.\d\d\b|B\.?S\.?\b|M\.?S\.?\b|Ph\.?\s?D|D in the University|I am (?:an?|currently)\b|[A-Z][\w-]+ [A-Z][\w-]+ is an? \w* ?Professor)', re.I)
AFFILIATION = re.compile(r'\b(?:University|Institute|Department|Dept|POSTECH|Professor|Director|Fellow|Academy|Association|School of)\b|대학교|대학원|학과', re.I)


def sentences(text):
    parts = []
    for part in SENTENCE_BREAK.split(text or ''):
        part = re.sub(r'\s+', ' ', part).strip(' -•·\t')
        # A period after 'Prof.' or a hard line break inside a sentence does not end the sentence.
        if parts and part and (ABBREVIATION_END.search(parts[-1]) or (OPEN_ENDED.search(parts[-1]) and not re.search(r'[.!?:]$', parts[-1]))
                               or (part[0].islower() and not re.search(r'[.!?:]$', parts[-1]))):
            parts[-1] += ' ' + part
        elif part:
            parts.append(part)
    return [part for part in parts if len(part) >= 15] or [re.sub(r'\s+', ' ', text or '').strip()]


def not_about_research(sentence):
    """Contact details, recruiting notices, career lines, affiliations and page furniture scraped with a homepage."""
    if NOT_RESEARCH.search(sentence) or CAREER_LINE.search(sentence):
        return True
    return len(sentence) < 90 and bool(AFFILIATION.search(sentence)) and not re.search(r'\b(?:study|studies|research|develop|focus|investigat|explor)', sentence, re.I)


def clip(text, limit=SNIPPET_LIMIT):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(mark) for mark in ('. ', '? ', '! '))
    if end >= limit // 2:  # whole sentences read better than a longer cut
        return cut[:end + 1]
    return (cut[:cut.rfind(' ')] if ' ' in cut[limit // 2:] else cut).rstrip(',;: ') + '…'


LINE_PREFIX = re.compile(r'^(?:\d+\s*주차\s*[:.]?|week\s*\d+\s*[:.]?|\d{1,2}\.\d{1,2}\s*\([^)]*\)|\d+\s*[.)]|[-•·*])\s*', re.I)
LINK_STOPWORDS = {'course', 'courses', 'student', 'students', 'understand', 'understanding', 'learn', 'learning', 'basic',
                  'basics', 'concept', 'concepts', 'fundamental', 'fundamentals', 'introduction', 'intro', 'overview',
                  'chapter', 'lecture', 'lectures', 'class', 'skills', 'ability', 'knowledge', 'principles', 'topics',
                  'various', 'including', 'their', 'these', 'other', 'using', 'based', 'such', 'will', 'with', 'from',
                  'that', 'this', 'which', 'have', 'into', 'about', 'also', 'more', 'what', 'midterm', 'final', 'exam',
                  'current', 'goal', 'practical', 'null', 'schedule', 'topic', 'support', 'area', 'perform', 'cover', 'principle', 'task', 'information', 'create', 'demonstrate', 'science', 'focus', 'provide', 'develop',
                  'review', 'project', 'research', 'study', 'studies', 'method', 'methods', 'theory', 'application',
                  'applications', 'approach', 'problem', 'problems', 'design', 'analysis', 'system', 'systems', 'model',
                  'models', 'data', 'part', 'parts', 'additional', 'techniques', 'technique', 'advanced', 'general',
                  '과목', '수업', '강의', '학생', '이해', '기초', '개념', '소개', '연구', '방법', '이론', '응용', '분석', '설계'}


def content_words(text):
    """Informative words for matching course text against lab material (lowercase, plural 's' dropped)."""
    words = set()
    for raw in re.findall(r'[A-Za-z][A-Za-z-]{3,}|[가-힣]{2,}', text or ''):
        word = raw.lower()
        if re.fullmatch(r'[가-힣]+', word):
            word = PARTICLE.sub('', word) if len(PARTICLE.sub('', word)) >= 2 else word
        elif word.endswith('s') and word[-2:] not in ('ss', 'is', 'us') and not word.endswith(('ies', 'ses')) and len(word) > 4:
            word = word[:-1]
        if word not in LINK_STOPWORDS:
            words.add(word)
    return words


def course_lines(course):
    lines = []
    for field in ('description', 'lecture_plan'):
        for line in re.split(r'\n+|(?<=[.!?])\s+(?=[A-Z가-힣])', course.get(field) or ''):
            line = LINE_PREFIX.sub('', re.sub(r'\s+', ' ', line).strip()).strip()
            if len(line) >= 8 and not line.endswith(':') and content_words(line):
                lines.append(line)
    return list(dict.fromkeys(lines))


def snippet(text, variants=()):
    """The sentence that mentions the most query terms (else the first one), cut at a word boundary,
    and the exact spans of query terms inside it for highlighting."""
    parts = sentences(text)
    # A match runs to the end of the word, so 'robot' marks 'robotic' whole.
    patterns = [re.compile(r'\s?'.join(map(re.escape, v)) + r'\w*', re.I) for v in dict.fromkeys(variants) if len(v) >= 2]
    # A scraped page often opens with a heading ('Research Interests'); prefer a line long enough to say something.
    rank = lambda s: (sum(bool(p.search(s)) for p in patterns), not not_about_research(s), len(s) >= READABLE_SENTENCE, -parts.index(s))
    best = max(parts, key=rank)
    if rank(best)[:2] == (0, False):  # nothing here is worth quoting; the full text stays one click away
        return '', []
    best = clip(best)
    marks = list(dict.fromkeys(m.group(0) for p in patterns for m in p.finditer(best)))
    return best, marks


def load_lab_areas(path):
    """Research-area names written in each lab's own material (labs.jsonl), in source order.

    Returns {lab_id: (shown_areas, keys)} where `keys` match every research-area topic label the
    profile builder derived from this row (headings included), or None when the file is absent.
    Profile research-area topics outside `keys` are OpenAlex `core_topics`: they classify papers,
    they are not the lab's own words.
    """
    if not path.exists():
        return None
    areas = {}
    for row in load_jsonl(path):
        if not row.get('recommendable'):
            continue
        shown, keys = [], set()
        for area in row.get('research_areas') or []:
            raw = tidy(str(area.get('name_ko') or area.get('name_en') or area.get('name') or '').strip())
            keys.add(area_label(raw[:100]))
            label = area_label(raw)
            if area.get('kind') != 'heading' and label and label.lower() not in GENERIC_AREA_LABELS \
                    and label not in shown:
                shown.append(label)
        areas[row['id']] = (shown, keys)
    return areas


def informative_lab_name(lab_name, professors):
    """Return the lab's own name only when it says more than '<professor> 교수 연구실'."""
    name = (lab_name or '').strip()
    rest = name.lower()
    for professor in professors:
        professor = (professor or '').strip().lower()
        for form in (professor, professor.split(' (')[0].strip()):
            if form:
                rest = rest.replace(form, '')
    return name if LAB_NAME_FILLER.sub('', rest) else ''


class CuratedCatalog:
    def __init__(self, data_dir):
        root = Path(data_dir)
        self.profiles = {p['lab_id']: p for p in load_jsonl(root / 'app_profiles.jsonl')}
        # A few professors are listed only by their English name (e.g. 'Sw Chung'); the profile builder
        # used to drop it. Filled here so the published profiles and their embeddings stay unchanged.
        english = {row['id']: row['professor'].get('name_en') for row in load_jsonl(root / 'labs.jsonl')
                   if not row['professor'].get('name_ko')} if (root / 'labs.jsonl').exists() else {}
        for lid, profile in self.profiles.items():
            profile['professors'] = [name or english.get(lid) or profile.get('lab_name') or '연구실'
                                     for name in profile['professors']]
        self.lab_areas = load_lab_areas(root / 'labs.jsonl')
        # Professors who share one lab homepage (vectorRAG D2): the search folds them into one card, which names them all.
        self.colleagues = {}
        if (root / 'labs.jsonl').exists():
            groups = {}
            for row in load_jsonl(root / 'labs.jsonl'):
                if row.get('recommendable') and row['id'] in self.profiles:
                    info = row.get('lab') or {}
                    groups.setdefault(info.get('group') or info.get('url') or row['id'], []).append(row['id'])
            self.colleagues = {lid: [m for m in ids if m != lid] for ids in groups.values() if len(ids) > 1 for lid in ids}
        self.courses = [c for c in load_jsonl(root / 'courses.jsonl') if c.get('recommendable')]
        self.paper_years = {}
        if (root / 'papers.jsonl').exists():
            for row in load_jsonl(root / 'papers.jsonl'):
                for paper in row.get('papers') or []:
                    if paper.get('doi') and paper.get('year'):
                        self.paper_years['https://doi.org/' + paper['doi'].lower()] = paper['year']
        self.course_map = {c['code']: c for c in self.courses}
        self.labs = self.profiles
        self.aliases = {lid: lid for lid in self.profiles}
        legacy = root / 'legacy_lab_aliases.json'
        if legacy.exists():
            # Accounts and reviews made before the curated switch still name the old 4-department IDs.
            for old, new in json.loads(legacy.read_text(encoding='utf-8'))['aliases'].items():
                if new in self.profiles:
                    self.aliases.setdefault(old, new)
        self.mark_suspect(root / 'suspect_papers.json')
        for profile in self.profiles.values():
            for topic in profile['topics']:
                topic['label_ko'], topic['quote'] = tidy(topic['label_ko']), tidy(topic['quote'])
        for course in self.courses:
            for field in ('title', 'description', 'lecture_plan'):
                if isinstance(course.get(field), str):
                    course[field] = tidy(course[field])
        self._details = {}
        self._search_cache = {}
        path = root / 'lab_course_bge_m3.json'
        self.course_similarity = {}
        if path.exists():
            mapping = json.loads(path.read_text(encoding='utf-8'))
            sources = mapping.get('sources') or {}
            if sources and all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
                               for name, digest in sources.items()):
                self.course_similarity = mapping.get('labs', {})

    def mark_suspect(self, path):
        """Flag papers that likely belong to a namesake of the professor (tools/build_suspect_papers.py). The topics stay
        in place because the stored embeddings refer to them by position; search, cards and evidence skip them."""
        self.suspect_titles = {}
        if path.exists():
            self.suspect_titles = {lid: {p['title'] for p in papers} for lid, papers in json.loads(path.read_text(encoding='utf-8'))['labs'].items()}
        for lid, titles in self.suspect_titles.items():
            for t in self.profiles.get(lid, {}).get('topics', []):
                t['suspect'] = t['section'] == 'representative_paper' and any(t['quote'].startswith(x[:60]) or t['label_ko'].startswith(x[:60]) for x in titles)

    @staticmethod
    def shown_topics(profile):
        return [t for t in profile['topics'] if not t.get('suspect')]

    def resolve(self, lab_id):
        return self.aliases[lab_id]

    def primary_topics(self, lab_id):
        return self.profiles[self.resolve(lab_id)]['topics']

    def overview(self, profile):
        """Short research overview for cards and the detail sidebar.

        Prefers the research areas written in the lab's own material. Without them it falls back
        to OpenAlex paper classifications or representative paper titles, and says which it is.
        """
        lid = profile['lab_id']
        area_topics = [area_label(t['label_ko']) for t in profile['topics'] if t['section'] == 'research_area']
        if self.lab_areas is None:  # no labs.jsonl next to the profiles: keep the profile's own labels
            lab_areas = [a for a in dict.fromkeys(area_topics) if a and a.lower() not in GENERIC_AREA_LABELS]
            classified = []
        else:
            lab_areas, own = self.lab_areas.get(lid, ([], set()))
            classified = [a for a in dict.fromkeys(area_topics)
                          if a and a not in own and a.lower() not in GENERIC_AREA_LABELS]
        if lab_areas:
            return {'source': 'lab_material', 'title': '연구 분야', 'items': lab_areas,
                    'note': '연구실 자료에 적힌 분야예요.', 'classification': classified}
        if classified:
            return {'source': 'openalex_topic', 'title': '대표 논문의 주제 분류', 'items': classified,
                    'note': 'OpenAlex가 논문에 붙인 분류예요. 연구실이 직접 밝힌 분야는 아닙니다.',
                    'classification': []}
        titles = [t['label_ko'].strip() for t in self.shown_topics(profile)
                  if t['section'] == 'representative_paper' and t['label_ko'].strip()]
        if titles:
            return {'source': 'paper_title', 'title': '대표 논문', 'items': titles,
                    'note': '연구실 자료에 분야 목록이 없어 대표 논문 제목을 보여드려요.', 'classification': []}
        return {'source': 'none', 'title': '연구 분야', 'items': [],
                'note': '원문 자료에서 연구 내용을 확인해 주세요.', 'classification': []}

    @staticmethod
    def summary_text(overview, limit=3):
        """Plain-text form of the overview, kept for API clients that read `summary`."""
        items = overview['items']
        if not items:
            return overview['note']
        rest = len(items) - limit
        return f"{overview['title']}: " + ' · '.join(items[:limit]) + (f' 외 {rest}개' if rest > 0 else '')

    @staticmethod
    def topic_label(t):
        # The builder labels the homepage-intro topic with the lab name; show what it is instead.
        return '연구실 소개' if t['section'] == 'research_intro' else t['label_ko']

    def card(self, lab_id):
        p = self.profiles[self.resolve(lab_id)]
        topics = [{'id': t['concept'], 'label': self.topic_label(t), 'role': t['role'],
                   'weight': t['weight'], 'scope': t['scope'], 'section': t['section']} for t in self.shown_topics(p)]
        overview = self.overview(p)
        professors = list(dict.fromkeys(p['professors'] + [n for m in self.colleagues.get(p['lab_id'], []) for n in self.profiles[m]['professors']]))
        return {'id': p['lab_id'], 'professors': professors, 'lab_name': p['lab_name'],
                'lab_subtitle': informative_lab_name(p['lab_name'], professors), 'department': p['department'],
                'url': next(iter(safe_urls([p['lab_url']])), ''), 'topics': topics,
                'overview': overview, 'summary': self.summary_text(overview),
                'status': p['status'], 'evidence_grade': 'curated',
                'quality_flags': [], 'review_notes': []}

    def _evidence(self, t, variants=()):
        """Source passage for display: kind, title, one or two sentences (preferring ones with the query terms),
        and the full text for an optional 'show all'."""
        label, quote, section = self.topic_label(t), t['quote'], t['section']
        title, body = label, quote
        if section == 'representative_paper':
            head = t['label_ko']
            end = quote.find('. ', len(head) - 1 if len(head) < 100 else 60) if quote.startswith(head[:60]) else -1
            title, body = (quote[:end], quote[end + 2:]) if end > 0 else (head, quote)
        elif section == 'research_area' or quote.strip() == label.strip():
            body = ''
        text, marks = snippet(body, variants) if body else ('', [])
        urls = safe_urls(t['source_urls'])
        year = next((self.paper_years[u.lower()] for u in urls if u.lower() in self.paper_years), None)
        return {'topic': t['concept'], 'label': label, 'text': quote, 'urls': urls, 'section': section, 'role': t['role'],
                'kind': EVIDENCE_KIND.get(section, '연구 자료'), 'title': title, 'snippet': text, 'marks': marks,
                'full': body if body and body != text else '', 'year': year}

    def _search_text(self, topic):
        key = id(topic)
        if key not in self._search_cache:
            self._search_cache[key] = re.sub(r'\s+', '', (topic['label_ko'] + ' ' + topic['quote']).lower())
        return self._search_cache[key]

    def _within_a_word(self, term, topic):
        """Spaces are ignored when matching, so a short plain Korean word could be formed across two words
        ('식물인 체관' for 인체). Those words must appear unbroken in the original text."""
        if term in EXPANSIONS or len(term) > 3 or not re.fullmatch(r'[가-힣]+', term):
            return True
        return term in topic['label_ko'] or term in topic['quote']

    def search(self, interests):
        """Labs whose own material contains the query words. Known research terms (with English variants)
        outweigh other words, rare words outweigh common ones, and repeated mentions in a lab count a little."""
        terms = search_terms(interests)
        if not terms:
            return []
        hits = {}
        for lid, p in self.profiles.items():
            for t in self.shown_topics(p):
                text = self._search_text(t)
                for term, variants in terms.items():
                    if any(v in text for v in variants) and self._within_a_word(term, t):
                        hits.setdefault(lid, {}).setdefault(term, []).append(t)
        total = len(self.profiles)
        df = {term: sum(term in found for found in hits.values()) for term in terms}
        informative = {term for term in terms if df[term] and df[term] <= total * COMMON_FRACTION}
        weight = {term: math.log((total + 1) / (df[term] + 1)) * (2 if term in EXPANSIONS else 1)
                  * (1 if term in informative or not informative else 0.2) for term in terms}
        found = []
        for lid, by_term in hits.items():
            if informative and not informative & set(by_term):
                continue  # only common words matched
            topics = list({id(t): t for ts in by_term.values() for t in ts}.values())
            card = self.card(lid)
            card.update(matched_topics=[t['concept'] for t in topics[:3]],
                        evidence=[self._evidence(t, [v for vs in terms.values() for v in vs]) for t in topics[:3]],
                        score=round(sum(weight[term] * (1 + math.log(len(ts))) for term, ts in by_term.items()), 3),
                        strong=any(term in EXPANSIONS for term in by_term), connection='direct', reason='연구실 자료에서 입력한 표현과 일치하는 내용을 찾았습니다.')
            found.append(card)
        return sorted(found, key=lambda c: (-c['score'], c['professors'][0]))[:20]

    def courses_named(self, phrases, cue):
        """[(course, exact)] a query names. A phrase equal to a course title ('선형대수' → 선형대수학) always counts;
        a word inside longer titles ('선형대수' → 응용선형대수) only when the query says 수업·과목·강의."""
        if not hasattr(self, '_course_bases'):
            self._course_bases = [(course_base(c['title']), c) for c in self.courses]
        exact, partial = [], []
        for phrase in phrases:
            words = [PARTICLE.sub('', w) if len(w) > 2 else w for w in COURSE_WORD.sub(' ', phrase).split()]
            keys = [''.join(words)] + (words if cue and len(words) > 1 else [])
            for key in keys:
                key = COURSE_ALIASES.get(key, key)
                if len(key) < 2:
                    continue
                exact += [c for base, c in self._course_bases if base in (key, key + '학')]
                if cue or any(base in (key, key + '학') for base, _ in self._course_bases):
                    partial += [c for base, c in self._course_bases if len(key) >= 3 and key in base]
        named = {c['code']: (c, True) for c in exact}
        for c in sorted(partial, key=lambda c: c['code'][4:]):
            named.setdefault(c['code'], (c, False))
        return list(named.values())[:COURSE_LIMIT]

    def course_labs(self, named):
        """{lab_id: (score, course, 'teaches'|'similar')}: labs of the course's instructors, then labs whose
        material is close to the course in BGE-M3 (`lab_course_bge_m3.json`). Neither is a prerequisite claim."""
        found = {}
        for course, exact in named:
            bonus = EXACT_BONUS if exact else 0.0
            values = [sims[course['code']] for lid, sims in self.course_similarity.items()
                      if lid in self.profiles and course['code'] in sims]
            threshold = max(values, default=0) * SIMILAR_RATIO
            department = (course.get('department') or {}).get('name') or ''
            for lid, sims in self.course_similarity.items():
                if course['code'] in sims and lid in self.profiles and sims[course['code']] >= threshold:
                    same_department = department and department in self.profiles[lid].get('department', '').split(' · ')
                    found.setdefault(lid, []).append((sims[course['code']] + bonus + (DEPARTMENT_BONUS if same_department else 0), course, 'similar'))
            for professor in course.get('professors') or []:
                lid = professor.get('lab_id')
                if lid in self.profiles and professor.get('basis') != 'not_in_lab_data':
                    sim = self.course_similarity.get(lid, {}).get(course['code'], TEACHER_BASE)
                    found.setdefault(lid, []).append((sim + TEACHER_BONUS + bonus, course, 'teaches'))
        best = {lid: max(links, key=lambda link: (link[2] == 'teaches', link[0])) for lid, links in found.items()}
        return dict(sorted(best.items(), key=lambda kv: (kv[1][2] != 'teaches', -kv[1][0]))[:COURSE_LAB_LIMIT])

    def course_card(self, lab_id, course, kind, card=None):
        card = dict(card or self.card(lab_id))
        name = f"‘{course['title']}’({course['code']})"
        card['reason'] = (f'{name} 수업을 맡은 교수의 연구실이에요.' if kind == 'teaches' else
                          f'{name} 수업 설명과 연구실 자료의 의미가 가까워요. 자동 계산이라 실제 관련성은 원문에서 확인하세요.')
        about = re.sub(r'\s+', ' ', course.get('description') or '').strip()
        lines = course_lines(course)
        course_evidence = [{'topic': 'course', 'label': course['title'], 'text': about, 'urls': [], 'section': 'course',
                            'role': 'course', 'kind': EVIDENCE_KIND['course'], 'title': f"{course['title']} ({course['code']})",
                            'snippet': clip(' · '.join(lines[:2]) if lines else about), 'marks': [], 'full': '',
                            'year': None}] if about or lines else []
        card['evidence'] = course_evidence + list(card.get('evidence') or [])[:2]
        card['connection'] = 'course'
        return card

    def detail(self, lab_id):
        lid = self.resolve(lab_id)
        if lid in self._details:
            return self._details[lid]
        p = self.profiles[lid]
        ranked = sorted(self.course_similarity.get(lid, {}).items(), key=lambda kv: -kv[1])[:20]
        courses, by_title = [], {}
        for code, similarity in ranked:
            c = self.course_map.get(code)
            if not c:
                continue
            same = COURSE_PREFIX.sub('', c['title'])
            if same in by_title:  # one class listed under two departments, sometimes with a '특강:' prefix
                by_title[same]['other_codes'].append(code)
                continue
            evidence = (c.get('description') or c.get('lecture_plan') or '').strip()
            link = self.course_link(lid, c)
            reason = (f"연구실의 {link['lab_kind']}에 나오는 {', '.join(link['shared'][:3])} 내용을 이 과목에서도 다뤄요."
                      if link else '과목 설명과 연구실 자료의 전반적인 내용이 비슷해 고른 과목이에요. 겹치는 표현은 따로 찾지 못했어요.')
            courses.append({'id': code, 'code': code, 'other_codes': [], 'name': c['title'],
                            'description': clip(evidence, 1500), 'topics': [], 'reason': reason, 'link': link,
                            'intro': [clip(line) for line in course_lines(c)[:2]],
                            'evidence': clip(evidence, 1500), 'strength': 'semantic',
                            'quality_flags': c.get('exclusion') or [], 'similarity': similarity})
            by_title[same] = courses[-1]
        result = {**self.card(lid), 'evidence': [self._evidence(t) for t in self.shown_topics(p)],
                  'courses': courses,
                  'notice': '과목은 BGE-M3 의미 유사도에 따른 탐색 후보입니다. 공식 선수과목이나 연구실 참여 조건이 아닙니다.'}
        self._details[lid] = result
        return result

    def _lab_word_df(self):
        if not hasattr(self, '_word_df'):
            df = {}
            for p in self.profiles.values():
                for word in set().union(*[content_words(t['label_ko'] + ' ' + t['quote']) for t in self.shown_topics(p)] or [set()]):
                    df[word] = df.get(word, 0) + 1
            self._word_df = df
        return self._word_df

    def course_link(self, lab_id, course):
        """The course line and lab passage that share the most informative words, or None. Words used by more than
        COMMON_FRACTION of labs are ignored, so 'learning' or 'materials' alone never make a link."""
        df, total = self._lab_word_df(), len(self.profiles)
        topics = [(t, content_words(t['label_ko'] + ' ' + t['quote'])) for t in self.shown_topics(self.profiles[lab_id])]
        best = None
        for line in course_lines(course):
            for t, words in topics:
                shared = [w for w in content_words(line) & words if df.get(w, 0) <= total * COMMON_FRACTION]
                if shared:
                    score = sum(math.log((total + 1) / (df.get(w, 0) + 1)) for w in shared)
                    if not best or score > best[0]:
                        best = (score, line, t, sorted(shared, key=lambda w: df.get(w, 0)))
        if not best:
            return None
        _, line, t, shared = best
        evidence = self._evidence(t, shared)
        lowered = line.lower()  # 'machine' or 'deep' alone says little when the course says 'machine learning'
        shared = list(dict.fromkeys(f'{w} learning' if w in ('machine', 'deep') and f'{w} learning' in lowered else w for w in shared))
        return {'course_line': clip(line), 'course_full': line if clip(line) != line else '', 'lab_full': evidence['full'], 'shared': shared[:4], 'lab_kind': evidence['kind'],
                'lab_title': evidence['title'], 'lab_snippet': evidence['snippet'], 'lab_marks': evidence['marks'],
                'course_marks': list(dict.fromkeys(m.group(0) for w in shared for m in re.finditer(re.escape(w) + r'\w*', line, re.I)))}

    def guide(self, lab_id, selected_ids):
        detail = self.detail(lab_id)
        if not isinstance(selected_ids, list) or any(not isinstance(x, str) for x in selected_ids):
            raise ValueError('수강 과목 목록이 올바르지 않습니다.')
        related = {c['id']: c for c in detail['courses']}
        if any(code not in related for code in selected_ids):
            raise ValueError('이 연구실에 제시된 과목만 선택할 수 있습니다.')
        selected = [related[code] for code in dict.fromkeys(selected_ids)]
        missing = [c for c in detail['courses'] if c['id'] not in selected_ids]
        now, later = [], []
        for t in self.shown_topics(self.profiles[detail['id']])[:3]:
            ev = self._evidence(t)
            label = self.topic_label(t)
            now.append({'title': f'{label} 자료 살펴보기', 'difficulty': '입문 탐색',
                        'basis': '원문과 논문 제목에서 실제 연구 문제를 먼저 확인해 보세요.',
                        'steps': ['원문에서 연구 문제 하나를 고릅니다.', '사용한 방법과 아직 모르는 개념을 구분합니다.',
                                  '선택한 과목의 설명과 연결되는지 직접 확인합니다.'],
                        'evidence': [ev], 'courses': []})
            later.append({'title': f'{label}의 학습 준비', 'difficulty': '추가 확인 필요',
                          'basis': '과목의 의미 유사도만으로 필요한 역량이나 참여 자격을 판단할 수 없습니다.',
                          'steps': ['아래 과목의 강의목표와 진도 내용을 확인합니다.',
                                    '실제 연구에 필요한 지식은 연구실 자료와 지도교수에게 확인합니다.'],
                          'evidence': [ev], 'courses': missing[:4],
                          'self_study': '원문 읽기와 기초 개념 정리부터 시작해 보세요.'})
        return {'lab_id': detail['id'], 'selected_courses': selected, 'recommended_courses': missing,
                'start_now': now, 'prepare_next': later, 'insufficient_evidence': not bool(now),
                'notice': '학습 후보를 제시한 것이며 공식 선수과목·숙련도·참여 허가를 뜻하지 않습니다.'}
