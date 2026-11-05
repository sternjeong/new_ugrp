"""Source-backed, deterministic retrieval. No claims of model-based personalization."""
import json
from functools import lru_cache
import re
from pathlib import Path
from urllib.parse import urlsplit

# Bilingual retrieval vocabulary, not inferred student competencies.
TOPICS = {
    'ai': ('AI·기계학습', 'method', ['인공지능', '기계학습', '머신러닝', '딥러닝', 'ai', 'artificial intelligence', 'machine learning', 'deep learning', 'neural network']),
    'biology': ('생명과학', 'domain', ['생명과학', '생물', '유전', 'biology', 'biological', 'genomic', 'genomics', 'protein', 'bioinformatics', '생명']),
    'medicine': ('의료·건강', 'domain', ['의료', '의학', '건강', 'medical', 'healthcare', 'biomedical', 'clinical', 'disease', '뇌질환']),
    'vision': ('영상·컴퓨터비전', 'method', ['컴퓨터비전', '영상처리', 'computer vision', 'image processing', 'imaging', 'vision']),
    'robotics': ('로봇', 'domain', ['로봇', 'robot', 'robots', 'robotics', 'robotic', 'autonomous', '자율주행']),
    'semiconductor': ('반도체·소자', 'domain', ['반도체', '소자', 'semiconductor', 'transistor', 'transistors', 'electronic device', 'nano device']),
    'circuits': ('회로·하드웨어', 'method', ['회로', '하드웨어', 'circuit', 'circuits', 'hardware', 'vlsi', 'integrated circuit']),
    'communications': ('통신·네트워크', 'domain', ['통신', '네트워크', 'communication', 'communications', 'wireless', 'networking', 'iot']),
    'systems': ('컴퓨터 시스템', 'domain', ['컴퓨터구조', '운영체제', '시스템소프트웨어', 'computer architecture', 'operating system', 'computer systems', 'distributed systems']),
    'data': ('데이터 분석', 'method', ['데이터', '데이타', 'database', 'data mining', 'data analysis', 'big data', '데이터베이스', '데이타베이스']),
    'security': ('보안', 'domain', ['보안', '암호', 'security', 'cryptography', 'privacy', 'cybersecurity']),
    'math': ('수학·최적화', 'method', ['수학', '미적분', '선형대수', '최적화', 'optimization', 'mathematics', 'linear algebra', 'calculus', 'numerical']),
    'statistics': ('통계·확률', 'method', ['통계', '확률', 'statistics', 'statistical', 'probability', 'probabilistic']),
    'signal': ('신호처리·제어', 'method', ['신호처리', '제어', 'signal processing', 'control theory', 'radar', '레이더', '레이더', 'feedback control']),
    'materials': ('신소재·나노', 'domain', ['신소재', '재료', '나노', 'materials', 'nanomaterial', 'nanotechnology', 'nanostructure']),
    'energy': ('에너지·환경', 'domain', ['에너지', '환경공학', '환경오염', '기후', '배터리', 'energy', 'battery', 'batteries', 'environmental', 'renewable', 'solar']),
    'physics': ('물리·양자', 'domain', ['물리', '양자', 'physics', 'quantum', 'photonics', 'optics', '광학']),
    'chemistry': ('화학', 'domain', ['화학', 'chemistry', 'chemical', 'catalysis', 'molecular']),
    'programming': ('프로그래밍·알고리즘', 'method', ['프로그래밍', '알고리즘', '코딩', 'programming', 'algorithm', 'algorithms', 'software engineering']),
    'design': ('인터랙션·디자인', 'domain', ['디자인', '인터랙션', '사용자경험', 'human computer interaction', 'interaction design', 'hci', 'virtual reality', '가상현실']),
}


@lru_cache(maxsize=512)
def pattern(term):
    if re.fullmatch(r'[a-z0-9 .-]+', term):
        return re.compile(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', re.I)
    return re.compile(re.escape(term), re.I)


def matches(text, term):
    return pattern(term).search(text) is not None


def topics_for(text):
    return {key for key, (_, _, terms) in TOPICS.items() if any(matches(text, term) for term in terms)}


def homepage(url):
    parsed = urlsplit(url)
    return (parsed.netloc.lower().removeprefix('www.') + parsed.path.rstrip('/')).lower()


def safe_urls(values):
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and urlsplit(v).scheme in ('http', 'https') and urlsplit(v).netloc))


def excerpt(text, terms):
    """A contiguous original substring, never an invented summary."""
    lower = text.lower()
    positions = [match.start() for t in terms if (match := pattern(t).search(text))]
    positions = [p for p in positions if p >= 0]
    pos = min(positions) if positions else 0
    start = max(0, text.rfind('\n', max(0, pos - 90), pos) + 1)
    if pos - start > 100:
        start = max(0, pos - 80)
    return text[start:min(len(text), pos + 240)].strip()


def research_text(text):
    # Source labels are crawler guesses: reject contact-only and student-directory pages.
    if re.search(r'researchers and students|research\s*&\s*admin staff', text[:180], re.I):
        return ''
    return re.split(r'(?im)^\s*#*\s*(?:teaching|publications|selected publications|journal publications|address:|contact us|copyright.*|personal information policy.*)\s*$', text, maxsplit=1)[0]


def load_rows(root):
    root = Path(root)
    try:
        labs = [json.loads(line) for line in (root / 'labs.jsonl').read_text().splitlines() if line.strip()]
        courses = [json.loads(line) for line in (root / 'courses.jsonl').read_text().splitlines() if line.strip()]
    except FileNotFoundError as exc:
        raise RuntimeError('data/labs.jsonl과 data/courses.jsonl이 필요합니다. data/README.md를 확인하세요.') from exc
    return labs, courses


def group_collected(rows):
    """Group professor-level records that share a homepage into one candidate unit."""
    labs, aliases, groups = {}, {}, {}
    for row in rows:
        if row.get('data_status') != 'collected':
            continue
        group = homepage(row['lab_url'])
        # Both snapshots identify the Machine Learning Lab @ POSTECH.
        if group in ('ml.postech.ac.kr', 'ml-postech.github.io'):
            group = 'ml.postech.ac.kr'
        if group in groups:
            canonical = groups[group]
            labs[canonical]['members'].append(row)
            aliases[row['record_id']] = canonical
        else:
            canonical = row['record_id']
            groups[group] = canonical
            aliases[canonical] = canonical
            labs[canonical] = {'members': [row]}
    return labs, aliases


class Catalog:
    def __init__(self, data_dir):
        rows, self.courses = load_rows(data_dir)
        self.labs, self.aliases = group_collected(rows)
        for item in self.labs.values():
            item['topics'] = {}
            for member in item['members']:
                available = member.get('sections', {})
                kinds = ('research_intro', 'unclassified') if any(available.get(k, {}).get('text') for k in ('research_intro', 'unclassified')) else ('publications',)
                for kind in kinds:
                    section = member.get('sections', {}).get(kind)
                    if not section:
                        continue
                    text = section.get('text', '')
                    # Do not use teaching catalogues or historical paper lists as current research descriptions.
                    if kind != 'publications':
                        text = research_text(text)
                    for key in topics_for(text):
                        if key not in item['topics']:
                            item['topics'][key] = {'topic': key, 'label': TOPICS[key][0], 'text': excerpt(text, TOPICS[key][2]), 'urls': safe_urls(section.get('source_urls', [])), 'section': kind}
        self.course_topics = {}
        self.course_map = {}
        for c in self.courses:
            cid = c['record_id']
            self.course_map[cid] = c
            title = c.get('course_name_kr', '') + ' ' + c.get('course_name_en', '')
            body = ' '.join(c.get(k, '') or '' for k in ('description', 'objectives'))
            title_topics = topics_for(title)
            self.course_topics[cid] = title_topics | {k for k, (_, _, terms) in TOPICS.items() if sum(bool(pattern(t).search(body)) for t in terms) >= 2}
        self._details = {}

    def resolve(self, lab_id):
        return self.aliases[lab_id]

    def card(self, lab_id):
        canonical = self.resolve(lab_id)
        item = self.labs[canonical]
        members = item['members']
        return {'id': canonical, 'professors': [r['professor_name'] for r in members], 'department': members[0]['department'], 'url': next(iter(safe_urls([members[0]['lab_url']])), ''), 'topics': [{'id': key, 'label': TOPICS[key][0], 'role': TOPICS[key][1]} for key in TOPICS if key in item['topics']], 'quality_flags': list(dict.fromkeys(flag for r in members for flag in r.get('quality_flags', []))), 'review_notes': [note.get('reason', '') for r in members for note in r.get('review_notes', [])]}

    def search(self, interests):
        interests = interests.strip()
        if not interests:
            return []
        wanted = topics_for(interests)
        if '환경' in interests:
            wanted.add('energy')
        # A named course can supply topic context without claiming it was taken.
        for c in self.courses:
            name = c.get('course_name_kr', '')
            if len(name) >= 3 and name in interests:
                wanted |= self.course_topics[c['record_id']]
        literals = [w.lower() for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', interests) if w not in {'관심', '관심이', '있어요', '싶어요', '연구', '공부', '하고', '분야', '대한'}]
        results = []
        for lid, item in self.labs.items():
            found = [key for key in TOPICS if key in wanted and key in item['topics']]
            evidence = [item['topics'][key] for key in found]
            if not wanted and literals:
                for member in item['members']:
                    for kind in ('research_intro', 'unclassified'):
                        section = member.get('sections', {}).get(kind, {})
                        text = research_text(section.get('text', ''))
                        matched = [w for w in literals if matches(text, w)]
                        if matched:
                            evidence.append({'topic': None, 'label': ', '.join(matched), 'text': excerpt(text, matched), 'urls': safe_urls(section.get('source_urls', [])), 'section': kind})
            if not evidence:
                continue
            card = self.card(lid)
            card['matched_topics'] = found
            card['evidence'] = evidence
            card['connection'] = 'domain_method' if any(TOPICS[k][1] == 'domain' for k in found) and any(TOPICS[k][1] == 'method' for k in found) else 'direct'
            card['reason'] = ' · '.join(e['label'] for e in evidence) + ' 관련 내용을 연구실 자료에서 찾았습니다.'
            if card['connection'] == 'domain_method':
                card['reason'] += ' 관심 도메인과 방법론을 함께 탐색할 후보입니다. 실제 활용 관계는 원문에서 확인하세요.'
            results.append(card)
        return sorted(results, key=lambda r: (-len(r['matched_topics']), r['professors'][0]))

    def detail(self, lab_id):
        lid = self.resolve(lab_id)
        if lid in self._details:
            return self._details[lid]
        item = self.labs[lid]
        courses = []
        for c in self.courses:
            shared = [key for key in TOPICS if key in self.course_topics[c['record_id']] and key in item['topics']]
            if not shared:
                continue
            title = c.get('course_name_kr', '') + ' ' + c.get('course_name_en', '')
            text = ' '.join(c.get(k, '') or '' for k in ('description', 'objectives', 'course_plan'))
            courses.append({'id': c['record_id'], 'code': c['course_code'], 'name': c.get('course_name_kr') or c.get('course_name_en'), 'description': c.get('description') or c.get('objectives') or '', 'topics': shared, 'reason': ' · '.join(TOPICS[k][0] for k in shared) + ' 지식을 연결해볼 수 있습니다.', 'evidence': excerpt(title + '\n' + text, [term for key in shared for term in TOPICS[key][2]]), 'quality_flags': c.get('quality_flags', []), '_rank': len(set(shared) & topics_for(title))})
        courses.sort(key=lambda c: (-c['_rank'], -len(c['topics']), c['code']))
        for c in courses:
            del c['_rank']
        result = {**self.card(lid), 'evidence': list(item['topics'].values()), 'courses': courses, 'notice': '내용상의 주제 연결을 제안합니다. 공식 선수과목이나 현재 모집 조건은 아닙니다.'}
        self._details[lid] = result
        return result

    def guide(self, lab_id, selected_ids):
        detail = self.detail(lab_id)
        if not isinstance(selected_ids, list) or any(not isinstance(i, str) for i in selected_ids):
            raise ValueError('수강 과목 목록이 올바르지 않습니다.')
        related = {c['id']: c for c in detail['courses']}
        if any(cid not in related for cid in selected_ids):
            raise ValueError('이 연구실에 제시된 과목만 선택할 수 있습니다.')
        selected = [related[cid] for cid in dict.fromkeys(selected_ids)]
        missing = [c for c in detail['courses'] if c['id'] not in selected_ids]
        known = {key for c in selected for key in c['topics']}
        topic_keys = sorted(self.labs[detail['id']]['topics'], key=lambda k: (k not in known, list(TOPICS).index(k)))
        now, later = [], []
        for key in topic_keys[:3]:
            label = TOPICS[key][0]
            ev = self.labs[detail['id']]['topics'][key]
            taken = [c for c in selected if key in c['topics']]
            prep = [c for c in missing if key in c['topics']]
            now.append({'title': f'{label} 연구의 문제와 접근법 비교', 'difficulty': '입문 탐색' if not taken else '수강 지식을 활용한 탐색', 'basis': (' · '.join(c['name'] for c in taken[:3]) + ' 수강 경험을 출발점으로 활용해볼 수 있습니다.') if taken else '관련 과목 수강을 확인하지 못했습니다. 용어 정리와 공개 연구 소개 읽기부터 시작해보세요.', 'steps': [f'아래 원문에서 {label} 관련 연구 문제 하나를 고릅니다.', '문제의 목적, 사용한 방법, 필요한 지식을 한 장으로 정리합니다.', '이해한 점과 확인할 질문을 구분해 다음 탐색의 기준으로 남깁니다.'], 'evidence': [ev], 'courses': []})
            later.append({'title': f'{label} 연구 방법의 공개 사례 재현·비교', 'difficulty': '추가 학습·자료 접근 확인 필요', 'basis': '현재 수강 표시만으로 재현 역량이나 연구실 참여 가능성을 판단할 수 없습니다. 실행 가능한 공개 사례와 필요한 환경을 먼저 확인하세요.', 'steps': [f'{label} 관련 기초 개념과 아래 과목의 연결 내용을 점검합니다.', '공개 코드·데이터 또는 문헌 사례가 있는지 확인하고 작은 재현 범위를 정합니다.', '변수를 하나 바꿔 비교할 수 있는지 검토하고 지도받을 질문을 정리합니다.'], 'evidence': [ev], 'courses': prep[:4], 'self_study': f'{label}의 기본 개념 → 원문에 나온 방법 → 작은 공개 사례 순서로 학습해보세요.'})
        return {'lab_id': detail['id'], 'selected_courses': selected, 'recommended_courses': missing, 'start_now': now, 'prepare_next': later, 'notice': '수강 선택에 근거한 탐색 가이드입니다. 숙련도 평가, 공식 연구 프로젝트 또는 참여 허가를 의미하지 않습니다.', 'insufficient_evidence': not bool(topic_keys)}
