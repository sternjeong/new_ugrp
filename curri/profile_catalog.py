"""Profile-based retrieval: reviewed lab/course profiles over a shared concept vocabulary.

Same interface as `catalog.Catalog` (resolve, card, search, detail, guide, courses, course_map)
so the server and the UI do not change. Still deterministic and source-backed: every lab
evidence item is a verbatim quote recorded in data/lab_profiles.jsonl, and every course link
is a shared concept with the excerpt that produced the course tag.
"""
import json
import hashlib
import re
from pathlib import Path
from .catalog import load_rows, group_collected, pattern, matches, safe_urls

GRADE_WEIGHT = {'research_intro': 1.0, 'unclassified': 1.0, 'reviewer_verified': 1.0, 'admission': 0.8, 'publications': 0.8, 'member_interests': 0.5, 'lab_name': 0.5, 'none': 0.0}
STATUS_WEIGHT = {'ok': 1.0, 'thin': 0.7, 'insufficient': 0.0}
# Broad concepts rank below specific ones when both match (reviewer rule: AI alone is a weak signal).
SPECIFICITY = {'machine_learning': 0.7, 'software_engineering': 0.6, 'statistics_probability': 0.8, 'optimization': 0.9}
STOPWORDS = {'관심', '관심이', '있어요', '싶어요', '연구', '공부', '하고', '분야', '대한', '관련', '해보고', '만드는', '같은', '재밌었어요', '수업', '기술', '문제', '좋아요', '괜찮아요'}


class ProfileCatalog:
    def __init__(self, data_dir):
        root = Path(data_dir)
        rows, self.courses = load_rows(root)
        self.labs, self.aliases = group_collected(rows)
        try:
            self.concepts = {c['id']: c for c in json.load(open(root / 'concepts.json'))['concepts']}
            profiles = [json.loads(l) for l in (root / 'lab_profiles.jsonl').read_text().splitlines() if l.strip()]
            course_profiles = [json.loads(l) for l in (root / 'course_profiles.jsonl').read_text().splitlines() if l.strip()]
        except FileNotFoundError as exc:
            raise RuntimeError('프로필 파일(concepts.json, lab_profiles.jsonl, course_profiles.jsonl)이 필요합니다. tools/ 스크립트로 생성하세요.') from exc
        self.profiles = {p['lab_id']: p for p in profiles}
        missing = set(self.labs) - set(self.profiles)
        if missing:
            raise RuntimeError(f'프로필이 없는 연구실: {sorted(missing)}')
        self.course_map = {c['record_id']: c for c in self.courses}
        self.course_profiles = {c['record_id']: c for c in course_profiles}
        mapping_file = root / 'lab_course_bge_m3.json'
        self.course_similarity = {}
        if mapping_file.is_file():
            mapping = json.loads(mapping_file.read_text(encoding='utf-8'))
            sources = mapping.get('sources', {})
            if sources and all(hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
                               for name, digest in sources.items()):
                self.course_similarity = mapping.get('labs', {})
        # concept id -> compiled keyword patterns (concept label parts count as keywords too)
        self.concept_patterns = {}
        for cid, c in self.concepts.items():
            terms = list(c['keywords']) + list(c.get('query_keywords', []))
            self.concept_patterns[cid] = [pattern(t.strip().lower()) for t in dict.fromkeys(t.strip() for t in terms if t.strip())]
        self._details = {}

    # ---- helpers ----
    def resolve(self, lab_id):
        return self.aliases[lab_id]

    def primary_topics(self, lab_id):
        return [t for t in self.profiles[lab_id]['topics'] if t.get('weight', 'primary') == 'primary']

    def concepts_in(self, text):
        text = text.lower()
        return {cid for cid, pats in self.concept_patterns.items() if any(p.search(text) for p in pats)}

    def card(self, lab_id):
        canonical = self.resolve(lab_id)
        prof = self.profiles[canonical]
        members = self.labs[canonical]['members']
        seen, topics = set(), []
        for t in prof['topics']:
            key = (t['concept'], t['role'])
            if key in seen:
                continue
            seen.add(key)
            topics.append({'id': t['concept'], 'label': t['concept_ko'], 'role': t['role'], 'weight': t.get('weight', 'primary'), 'scope': t.get('scope', 'core')})
        return {'id': canonical, 'professors': [r['professor_name'] for r in members], 'department': members[0]['department'],
                'url': next(iter(safe_urls([members[0]['lab_url']])), ''), 'topics': topics, 'summary': prof['summary_ko'],
                'status': prof['status'], 'evidence_grade': prof['evidence_grade'],
                'quality_flags': list(dict.fromkeys(flag for r in members for flag in r.get('quality_flags', []))),
                'review_notes': [note.get('reason', '') for r in members for note in r.get('review_notes', [])] + list(prof.get('notes', []))}

    @staticmethod
    def _evidence(t):
        return {'topic': t['concept'], 'label': t['label_ko'], 'text': t['quote'], 'urls': safe_urls(t.get('source_urls', [])), 'section': t['section'], 'role': t['role']}

    # ---- search ----
    def search(self, interests):
        interests = interests.strip()
        if not interests:
            return []
        wanted = self.concepts_in(interests)
        # A named course supplies its (title-level) concepts without claiming it was taken.
        for c in self.courses:
            name = c.get('course_name_kr', '') or ''
            if len(name) >= 3 and name in interests:
                wanted |= {x['concept'] for x in self.course_profiles.get(c['record_id'], {}).get('concepts', []) if x['strength'] == 'title'}
        literals = [w.lower() for w in re.findall(r'[A-Za-z]{3,}|[가-힣]{2,}', interests) if w not in STOPWORDS]
        results = []
        for lid, prof in self.profiles.items():
            if STATUS_WEIGHT.get(prof['status'], 0) == 0:
                continue
            grade = GRADE_WEIGHT.get(prof['evidence_grade'], 0.5)
            matched, evidence, score = [], [], 0.0
            if wanted:
                by_concept = {}
                for t in prof['topics']:
                    if t['concept'] in wanted and t['concept'] not in by_concept:
                        by_concept[t['concept']] = t
                primary = [t for t in by_concept.values() if t.get('weight', 'primary') == 'primary']
                if primary:
                    matched = [t['concept'] for t in primary]
                    evidence = [self._evidence(t) for t in primary]
                    # Secondary (generic method) topics add context only once a primary topic matched.
                    for t in by_concept.values():
                        if t.get('weight') == 'secondary':
                            matched.append(t['concept']); evidence.append(self._evidence(t)); score += 0.2
                    score += sum(SPECIFICITY.get(t['concept'], 1.0) for t in primary) + 0.5 * (len(primary) - 1)
            elif literals:
                hay = prof['summary_ko'] + ' ' + ' '.join(t['label_ko'] + ' ' + t['quote'] for t in prof['topics'])
                hit_words = [w for w in literals if matches(hay, w)]
                if hit_words:
                    for t in prof['topics']:
                        if any(matches(t['label_ko'] + ' ' + t['quote'], w) for w in hit_words):
                            evidence.append(self._evidence(t) | {'label': ', '.join(w for w in hit_words if matches(t['label_ko'] + ' ' + t['quote'], w)) or t['label_ko']})
                            if len(evidence) >= 3:
                                break
                    if not evidence:
                        continue
                    score = 0.3 * len(hit_words)
            if not evidence:
                continue
            score *= grade * STATUS_WEIGHT[prof['status']]
            card = self.card(lid)
            card['matched_topics'] = list(dict.fromkeys(matched))
            card['evidence'] = evidence
            card['score'] = round(score, 3)
            roles = {e['role'] for e in evidence if e['topic'] in matched}
            card['connection'] = 'domain_method' if {'domain', 'method'} <= roles else 'direct'
            labels = list(dict.fromkeys(e['label'] for e in evidence))
            card['reason'] = ' · '.join(labels[:4]) + ' 관련 내용을 연구실 자료에서 확인했습니다.'
            if card['connection'] == 'domain_method':
                card['reason'] += ' 관심 도메인과 방법론이 함께 나타나는 후보입니다. 실제 활용 관계는 원문에서 확인하세요.'
            if prof['status'] == 'thin':
                card['reason'] += ' 수집 자료가 제목 수준이라 연구 내용은 홈페이지에서 확인이 필요합니다.'
            results.append(card)
        return sorted(results, key=lambda r: (-r['score'], r['professors'][0]))

    # ---- detail: courses that share a primary concept ----
    def detail(self, lab_id):
        lid = self.resolve(lab_id)
        if lid in self._details:
            return self._details[lid]
        prof = self.profiles[lid]
        # Courses connect through the lab's core topics only; application topics (a side use of
        # the lab's methods) still matter for interest search but must not pull in another field's courses.
        lab_concepts = {}
        for t in self.primary_topics(lid):
            if t.get('scope', 'core') == 'core':
                lab_concepts.setdefault(t['concept'], t)
        courses = []
        for c in self.courses:
            cp = self.course_profiles.get(c['record_id'])
            if not cp:
                continue
            shared = [x for x in cp['concepts'] if x['concept'] in lab_concepts]
            if not shared:
                continue
            # A body-only mention of one concept is too weak for a lab with a broad profile.
            if not any(x['strength'] == 'title' for x in shared) and len(shared) < 2 and len(lab_concepts) > 3:
                continue
            strength = sum(2 if x['strength'] == 'title' else 1 for x in shared)
            labels = [self.concepts[x['concept']]['ko'] for x in shared]
            courses.append({'id': c['record_id'], 'code': c['course_code'], 'name': c.get('course_name_kr') or c.get('course_name_en'),
                            'description': c.get('description') or c.get('objectives') or '', 'topics': [x['concept'] for x in shared],
                            'reason': ' · '.join(labels) + ' 지식을 연결해볼 수 있습니다.', 'evidence': shared[0]['evidence'],
                            'strength': 'title' if any(x['strength'] == 'title' for x in shared) else 'body',
                            'quality_flags': c.get('quality_flags', []), '_rank': strength})
        # Only re-rank source-backed concept links. Dense similarity alone cannot establish
        # that a course teaches a skill required by a lab.
        similarity = self.course_similarity.get(lid, {})
        courses.sort(key=lambda c: (-c['_rank'], -similarity.get(c['id'], 0), c['code']))
        for c in courses:
            del c['_rank']
        result = {**self.card(lid), 'evidence': [self._evidence(t) for t in prof['topics']], 'courses': courses,
                  'notice': '연구실 프로필과 과목 설명이 공유하는 개념으로 연결한 제안입니다. 공식 선수과목이나 현재 모집 조건은 아닙니다.'}
        self._details[lid] = result
        return result

    # ---- guide ----
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
        by_concept = {}
        for t in self.primary_topics(detail['id']):
            by_concept.setdefault(t['concept'], t)
        ordered = sorted(by_concept.values(), key=lambda t: (t['concept'] not in known, t['role'] != 'domain'))
        now, later = [], []
        for t in ordered[:3]:
            label = t['label_ko']
            ev = self._evidence(t)
            taken = [c for c in selected if t['concept'] in c['topics']]
            prep = [c for c in missing if t['concept'] in c['topics']]
            now.append({'title': f'{label} 연구의 문제와 접근법 비교', 'difficulty': '입문 탐색' if not taken else '수강 지식을 활용한 탐색',
                        'basis': (' · '.join(c['name'] for c in taken[:3]) + ' 수강 경험을 출발점으로 활용해볼 수 있습니다.') if taken else '관련 과목 수강을 확인하지 못했습니다. 용어 정리와 공개 연구 소개 읽기부터 시작해보세요.',
                        'steps': [f'아래 원문에서 {label} 관련 연구 문제 하나를 고릅니다.', '문제의 목적, 사용한 방법, 필요한 지식을 한 장으로 정리합니다.', '이해한 점과 확인할 질문을 구분해 다음 탐색의 기준으로 남깁니다.'],
                        'evidence': [ev], 'courses': []})
            later.append({'title': f'{label} 연구 방법의 공개 사례 재현·비교', 'difficulty': '추가 학습·자료 접근 확인 필요',
                          'basis': '현재 수강 표시만으로 재현 역량이나 연구실 참여 가능성을 판단할 수 없습니다. 실행 가능한 공개 사례와 필요한 환경을 먼저 확인하세요.',
                          'steps': [f'{label} 관련 기초 개념과 아래 과목의 연결 내용을 점검합니다.', '공개 코드·데이터 또는 문헌 사례가 있는지 확인하고 작은 재현 범위를 정합니다.', '변수를 하나 바꿔 비교할 수 있는지 검토하고 지도받을 질문을 정리합니다.'],
                          'evidence': [ev], 'courses': prep[:4], 'self_study': f'{label}의 기본 개념 → 원문에 나온 방법 → 작은 공개 사례 순서로 학습해보세요.'})
        return {'lab_id': detail['id'], 'selected_courses': selected, 'recommended_courses': missing, 'start_now': now, 'prepare_next': later,
                'notice': '수강 선택에 근거한 탐색 가이드입니다. 숙련도 평가, 공식 연구 프로젝트 또는 참여 허가를 의미하지 않습니다.', 'insufficient_evidence': not bool(ordered)}
