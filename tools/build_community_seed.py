"""Build data/community_seed.json: dummy graduates, undergraduate reviewers, reviews and demo threads.

Everything here is fictional and marked `dummy: true` so it can be removed in one step.
Labs, topics and concept ids come from the real profiles; people and their words do not.
Deterministic (fixed seed), so re-running produces the same file.

    python3 tools/build_community_seed.py
"""
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DEMO_PASSWORD = 'curri-demo-2026'

SURNAMES = [('김', 'kim'), ('이', 'lee'), ('박', 'park'), ('최', 'choi'), ('정', 'jung'), ('강', 'kang'), ('조', 'cho'), ('윤', 'yoon'), ('장', 'jang'), ('임', 'lim'), ('한', 'han'), ('오', 'oh'), ('서', 'seo'), ('신', 'shin'), ('권', 'kwon'), ('황', 'hwang'), ('송', 'song'), ('류', 'ryu'), ('홍', 'hong'), ('문', 'moon')]
GIVEN = [('민', 'min'), ('서', 'seo'), ('지', 'ji'), ('현', 'hyun'), ('우', 'woo'), ('준', 'jun'), ('윤', 'yoon'), ('수', 'soo'), ('하', 'ha'), ('은', 'eun'), ('도', 'do'), ('연', 'yeon'), ('재', 'jae'), ('유', 'yu'), ('승', 'seung'), ('태', 'tae'), ('예', 'ye'), ('주', 'joo'), ('진', 'jin'), ('호', 'ho'), ('원', 'won'), ('채', 'chae'), ('나', 'na'), ('린', 'rin'), ('빈', 'bin')]
NICKNAMES = ['지곡동다람쥐', '새벽코딩러', '형산강러너', '효자시장단골', '무은재덕후', '연참새내기', '청암도서관지박령', '77번국도', '회로그리는곰', '로봇키우는중', '데이터콩', '포항물회', '노벨동산산책러', '체육관옆벤치', '밤샘납땜러', '텐서모양감자', '논문읽는펭귄', '랩실커피머신']
STUDENT_DEPTS = {
    'Computer Science': ['컴퓨터공학과', '컴퓨터공학과', '수학과', '산업경영공학과'],
    'Electrical Engineering': ['전자전기공학과', '전자전기공학과', '물리학과', '반도체공학과'],
    'IT Convergence': ['IT융합공학과', '전자전기공학과', '기계공학과', '생명과학과'],
    'Semiconductor Engineering': ['반도체공학과', '신소재공학과', '전자전기공학과'],
}
HARDWARE = {'semiconductor_devices', 'semiconductor_process_packaging', 'nanomaterials_2d', 'display_technology', 'circuit_design', 'rf_microwave', 'photonics_optics', 'thz_spectroscopy', 'power_electronics', 'soft_electronics', 'ultrasound_acoustics', 'bioelectronics_neural', 'biosensors', 'quantum', 'robotics', 'underwater_field_robotics', 'thermal_transport', 'materials_science', 'haptics', 'radar_sensing'}

ACTIVITY = {
    'sw': [
        '{t1} 관련 최근 논문을 매주 한 편씩 읽고 랩 세미나에서 요약 발표했어요. 후반 4주는 공개 코드로 {t2} 실험을 재현하는 일을 맡았습니다.',
        '선배 프로젝트에서 데이터 정리와 실험 자동화 스크립트를 담당했어요. {t1} 실험 결과를 표와 그래프로 정리하는 일이 많았습니다.',
        '논문에 나온 {t1} 방법을 직접 구현해 보고, 조건을 바꿔 가며 비교 실험을 했어요. 마지막 주에 결과 발표를 했습니다.',
        '처음 2주는 {t1} 기초 스터디, 이후에는 {t2} 관련 작은 문제를 받아 구현하고 매주 미팅에서 진행 상황을 공유했어요.',
    ],
    'hw': [
        '{t1} 측정 장비 사용법을 배우고, 선배와 함께 샘플을 측정해 데이터를 정리·분석했어요. 후반에는 {t2} 관련 시뮬레이션도 해봤습니다.',
        '{t1} 실험 보조로 시작해서 측정 자동화 파이썬 스크립트를 만들었어요. 매주 그룹 미팅에서 결과를 보고했습니다.',
        '{t1} 관련 기초 이론을 공부한 뒤, 시뮬레이션 툴로 {t2} 구조를 바꿔 가며 특성을 비교하는 일을 했어요.',
        '클린룸·실험실 안전 교육을 받고, 선배 공정을 옆에서 보조하며 {t1} 샘플 제작 과정을 익혔어요.',
    ],
}
GOOD = [
    '선배들이 질문을 편하게 받아줘서 모르는 걸 숨기지 않아도 됐어요. 매주 짧게라도 피드백을 받을 수 있었던 게 가장 좋았습니다.',
    '수업에서 배운 {t1} 개념이 실제 연구에서 어떻게 쓰이는지 처음으로 체감했어요. 논문 읽는 법을 제대로 배운 기회였습니다.',
    '교수님 미팅에서 학부생 발표도 진지하게 들어주셔서 동기부여가 많이 됐어요. 연구가 어떻게 굴러가는지 전체 흐름을 볼 수 있었습니다.',
    '학부생에게 맞는 크기의 과제를 주셔서 부담이 적었어요. 끝날 때쯤엔 {t2} 쪽으로 더 공부해 보고 싶다는 방향이 생겼습니다.',
    '연구실 분위기가 차분하고 서로 도와주는 편이에요. 실험이 막혔을 때 다른 선배들도 같이 봐주셨어요.',
    '진학 고민을 솔직하게 상담해 주셨어요. 대학원 생활이 실제로 어떤지 현실적으로 들을 수 있었던 게 큰 수확입니다.',
]
IMPROVE = {
    'common': [
        '처음 1~2주는 무엇을 해야 할지 막막했어요. 미리 {t1} 기초 자료를 읽고 가면 훨씬 수월할 것 같아요.',
        '선배들이 마감 기간에는 바빠서 질문 타이밍을 잡기 어려웠어요. 질문을 모아서 정해진 시간에 하는 게 좋습니다.',
        '참여 기간이 짧아서 결과까지 내기는 어려웠어요. 가능하면 한 학기 이상 하는 걸 추천해요.',
        '자율성이 큰 편이라 스스로 계획을 세우지 않으면 흘러가기 쉬워요. 주간 목표를 직접 정해 두는 걸 추천합니다.',
    ],
    'hw': ['장비 예약이 밀리면 대기 시간이 길었어요. 그 시간에 할 수 있는 분석 작업을 같이 받아두면 좋아요.'],
    'sw': ['GPU·서버 자원을 쓰는 순서가 정해져 있어서 실험이 몰리면 기다려야 했어요. 작은 규모로 먼저 검증해 두면 좋아요.'],
}
RECOMMEND = [
    '{t1}에 관심 있고 논문을 꾸준히 읽어볼 의지가 있는 학생', '진학을 고민 중이라 연구실 생활을 미리 경험해 보고 싶은 학생',
    '파이썬으로 데이터 다뤄본 경험이 조금이라도 있는 학생', '{t2} 쪽 수업이 재밌었던 2~3학년', '실험을 직접 손으로 해보고 싶은 학생',
]
TERMS = ['2024 겨울방학', '2025 봄학기', '2025 여름방학', '2025 가을학기', '2025 겨울방학', '2026 봄학기', '2026 여름방학']
TERM_DATES = {'2024 겨울방학': '2025-03-02', '2025 봄학기': '2025-06-25', '2025 여름방학': '2025-08-30', '2025 가을학기': '2025-12-20', '2025 겨울방학': '2026-03-01', '2026 봄학기': '2026-06-26', '2026 여름방학': '2026-08-29'}
DURATIONS = ['6주', '8주', '8주', '10주', '한 학기', '한 학기', '두 학기']
GRAD_INTRO = [
    '연구참여나 진학 고민 편하게 물어봐 주세요. 답장은 조금 늦을 수 있어요.',
    '학부생 때 연구참여로 이 연구실에 왔어요. 비슷한 고민 중이라면 경험 나눠드릴게요.',
    '실험·코드 관련 구체적인 질문 환영합니다.',
    '연구실 생활이나 수업 준비 관련해서 궁금한 점 있으면 연락 주세요.',
]
PROGRAMS = ['석사과정 1년차', '석사과정 2년차', '석박통합과정 2년차', '석박통합과정 3년차', '박사과정 2년차', '박사과정 4년차']


def stamp(day):
    return datetime.fromisoformat(day).replace(hour=12, tzinfo=timezone.utc).timestamp()


def main():
    rng = random.Random(2026)
    concepts = {c['id']: c for c in json.load(open(DATA / 'concepts.json'))['concepts']}
    profiles = [json.loads(l) for l in (DATA / 'lab_profiles.jsonl').read_text().splitlines() if l.strip()]
    labs = [p for p in profiles if p['status'] == 'ok' and len(p['topics']) >= 2]
    professors = {name.split(' (')[0] for p in profiles for name in p['professors']}
    used_names, used_emails, nicknames = set(), set(), list(NICKNAMES)
    rng.shuffle(nicknames)

    def person():
        while True:
            (s, sr), (g1, r1), (g2, r2) = rng.choice(SURNAMES), rng.choice(GIVEN), rng.choice(GIVEN)
            name = s + g1 + g2
            if g1 != g2 and name not in used_names and name not in professors:
                used_names.add(name)
                email = f'{r1}{r2}.{sr}@postech.example'
                if email not in used_emails:
                    used_emails.add(email)
                    return name, email

    chosen = rng.sample(labs, 22)
    graduates, students, reviews, threads = [], [], [], []
    for i, lab in enumerate(chosen):
        topic_ids = list(dict.fromkeys(t['concept'] for t in lab['topics']))
        labels = list(dict.fromkeys(t['label_ko'] for t in lab['topics']))
        for n in range(1 if i % 3 else 2):
            name, email = person()
            focus = labels[n % len(labels):][:2] or labels[:2]
            graduates.append({'key': f'grad{len(graduates) + 1:02d}', 'email': email, 'real_name': name, 'nickname': name, 'role': 'graduate', 'lab_id': lab['lab_id'],
                              'account': {'real_name': name, 'school': 'POSTECH', 'program': rng.choice(PROGRAMS), 'research': ' · '.join(focus),
                                          'interest_tags': topic_ids[:3], 'interest_text': '', 'headline': rng.choice(GRAD_INTRO), 'contact_consent': True}})
    for i in range(len(nicknames)):
        name, email = person()
        dept_pool = sum(STUDENT_DEPTS.values(), [])
        students.append({'key': f'stu{i + 1:02d}', 'email': email.replace('@', '.ug@'), 'real_name': name, 'nickname': nicknames[i], 'role': 'student',
                         'account': {'real_name': name, 'school': 'POSTECH', 'department': rng.choice(dept_pool), 'grade': rng.choice(['2학년', '3학년', '3학년', '4학년']),
                                     'goal': rng.choice(['research', 'graduate', 'explore']), 'interest_tags': [], 'interest_text': ''}})
    concept_ids = list(concepts)
    for s in students:
        s['account']['interest_tags'] = rng.sample(concept_ids, 2)
    for i, lab in enumerate(chosen[:18]):
        labels = list(dict.fromkeys(t['label_ko'] for t in lab['topics']))
        kind = 'hw' if any(t['concept'] in HARDWARE for t in lab['topics'][:2]) else 'sw'
        for author in rng.sample(students, rng.choice([1, 2, 2, 3, 3, 4])):
            t1, t2 = labels[0], labels[1 % len(labels)]
            term = rng.choice(TERMS)
            base = rng.choice([4, 4, 5, 5, 3])
            ratings = {k: max(2, min(5, base + rng.choice([-1, 0, 0, 0, 1]))) for k in ('mentoring', 'learning', 'workload', 'atmosphere')}
            fill = lambda text: text.format(t1=t1, t2=t2)
            reviews.append({'author': author['key'], 'lab_id': lab['lab_id'], 'term': term, 'duration': rng.choice(DURATIONS), 'activity': fill(rng.choice(ACTIVITY[kind])),
                            'ratings': ratings, 'good': fill(rng.choice(GOOD)), 'improve': fill(rng.choice(IMPROVE['common'] + IMPROVE[kind])), 'recommend_for': fill(rng.choice(RECOMMEND)),
                            'created': stamp(TERM_DATES[term]) + rng.randint(0, 20) * 86400})
    # Demo conversations so both inboxes have content on first launch.
    for n, (stu, grad) in enumerate([(students[0], graduates[0]), (students[1], graduates[3]), (students[2], graduates[0])]):
        lab_label = grad['account']['research'].split(' · ')[0]
        base = stamp('2026-09-20') + n * 86400
        messages = [{'from': stu['key'], 'body': f"안녕하세요, {stu['account']['department']} {stu['account']['grade']} {stu['nickname']}입니다. 3분커리에서 연구실을 알아보다 연락드려요. {lab_label} 연구에 관심이 생겼는데, 학부생 연구참여 전에 어떤 걸 공부해 두면 좋을지 여쭤보고 싶습니다!", 'created': base}]
        if n < 2:
            messages.append({'from': grad['key'], 'body': f'반가워요! {lab_label} 쪽은 관련 수업 하나 듣고, 연구실 홈페이지의 최근 논문 한두 편을 가볍게 읽어 보면 충분해요. 궁금한 점 정리해서 다시 보내 주면 더 자세히 알려줄게요.', 'created': base + 5 * 3600})
        threads.append({'student': stu['key'], 'graduate': grad['key'], 'subject': f'{lab_label} 연구참여 준비 질문', 'messages': messages})
    out = {'_about': '3분커리 프로토타입용 더미 커뮤니티 데이터(2026-10-01, tools/build_community_seed.py 생성). 인물·후기·대화는 모두 가상이며 dummy=true. 연구실 id와 주제 라벨만 실제 프로필에서 가져왔다. 이메일 도메인 postech.example은 수신 불가 주소다.',
           'dummy': True, 'demo_password': DEMO_PASSWORD, 'users': graduates + students, 'reviews': reviews, 'threads': threads}
    for row in out['users'] + out['reviews'] + out['threads']:
        row['dummy'] = True
    (DATA / 'community_seed.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print(f'graduates {len(graduates)} · students {len(students)} · reviews {len(reviews)} on {len({r["lab_id"] for r in reviews})} labs · threads {len(threads)}')


if __name__ == '__main__':
    main()
