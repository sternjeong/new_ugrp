"""Privacy policy, consent items and the operator slots they need.

The policy follows the items 개인정보 보호법 requires a 처리방침 to state (제30조, 시행령 제31조): purposes, items,
retention, provision to third parties, entrustment, 국외 이전 (제28조의8), destruction, data-subject rights, safety
measures (제29조), cookies, the privacy officer and remedies. Operator facts (name, officer, contact, dates) come from
`.local/privacy.json`; anything missing is shown as a visible 【입력 필요】 slot instead of an invented value.
This is a drafting aid, not legal advice: have it reviewed before real users sign up.
"""
import json
from pathlib import Path

POLICY_VERSION = '2026-11-07'
SLOTS = {
    'service_name': '3분커리',
    'operator': None,              # 운영 주체(팀·단체·개인 이름)
    'officer_name': None,          # 개인정보 보호책임자 성명
    'officer_position': None,      # 직책(예: 팀장)
    'officer_email': None,         # 연락 이메일
    'officer_phone': None,         # 연락처(선택)
    'effective_date': None,        # 시행일(YYYY-MM-DD)
    'hosting': 'Oracle Cloud Infrastructure (서버·데이터베이스 보관)',
    'site_url': 'https://3mincurri.duckdns.org',
}
MISSING = '【입력 필요: {}】'
SLOT_LABELS = {'operator': '운영 주체', 'officer_name': '개인정보 보호책임자 성명', 'officer_position': '책임자 직책',
               'officer_email': '책임자 이메일', 'officer_phone': '책임자 연락처', 'effective_date': '시행일'}

# 동의 항목: 필수와 선택을 나눠 받는다(제22조). 선택을 거부해도 서비스 이용은 막지 않는다(제16조 제3항, 제22조 제5항).
CONSENTS = {
    'terms': {'required': True, 'label': '이용 안내에 동의합니다'},
    'privacy': {'required': True, 'label': '개인정보 수집·이용(필수)에 동의합니다'},
    'age14': {'required': True, 'label': '만 14세 이상입니다'},
    'overseas': {'required': False, 'label': '의미 검색·AI 연구 가이드를 위한 국외 처리(선택)에 동의합니다'},
}
REQUIRED_CONSENTS = tuple(k for k, v in CONSENTS.items() if v['required'])


def load_slots(path):
    values = dict(SLOTS)
    if path and Path(path).is_file():
        values.update({k: v for k, v in json.loads(Path(path).read_text(encoding='utf-8')).items() if k in SLOTS and v})
    return values


def filled(values, key):
    return values.get(key) or MISSING.format(SLOT_LABELS.get(key, key))


def consent_notice():
    """What a person sees before agreeing (제15조 제2항: 목적·항목·기간·거부권과 불이익)."""
    return {
        'version': POLICY_VERSION,
        'items': CONSENTS,
        'required_summary': [
            {'purpose': '회원 식별, 로그인, 선배 연락·만남 약속, 후기와 질문 작성자 관리, 부정 이용 방지',
             'items': '이메일, 비밀번호(암호화 저장), 이름, 별명, 학교, 관심 분야',
             'retention': '탈퇴 시까지. 탈퇴 즉시 파기하되, 상대가 있는 쪽지는 보낸 사람을 ‘탈퇴한 사용자’로 바꿔 상대에게만 남긴다.'},
        ],
        'optional_summary': [
            {'purpose': '학과·학년·목표·자기소개 등 선배에게 전달할 추가 프로필', 'items': '입력한 항목만',
             'retention': '탈퇴 또는 삭제 시까지'},
            {'purpose': '의미 검색과 AI 연구 가이드(국외 처리)',
             'items': '검색 문장, 선택한 수강 과목, 학과·학년(이름·이메일은 보내지 않음)',
             'retention': '처리 후 국외 사업자 정책에 따름. 서비스는 결과만 보관'},
        ],
        'refusal': '필수 항목에 동의하지 않으면 회원 가입을 할 수 없습니다. 비회원으로 첫 연구실 탐색은 가능합니다. '
                   '국외 처리에 동의하지 않아도 가입할 수 있으며, 이 경우 사전 검색과 기본 가이드만 제공합니다.',
    }


def policy(values):
    v = lambda key: filled(values, key)
    sections = [
        ('1. 처리 목적', [
            '연구실 탐색과 추천, 탐색 기록 저장', '회원 가입·로그인·본인 확인(이메일 인증)과 비밀번호 재설정',
            '대학원생 선배와의 쪽지·만남 약속·익명 질문 답변 연결', '연구참여 후기와 질문 게시, 신고 처리와 부정 이용 방지',
            '쪽지·만남·관심 연구실 소식 알림 메일 발송', '서비스 개선을 위한 이용 통계(가명 처리)']),
        ('2. 처리 항목', [
            '필수: 이메일, 비밀번호(복원할 수 없게 암호화), 이름, 별명, 학교, 관심 분야',
            '선택: 학과, 복수전공, 학년, 연구참여 목표, 희망 시기, 한 줄 소개, 자기소개',
            '대학원생 선배: 소속 연구실, 과정, 연구 분야, 연락 허용 여부, 월 문의 상한, 가능 시간',
            '자동 수집: 세션 쿠키, 접속 IP(요청 제한과 보안 목적, 저장하지 않음), 가명 처리된 이용 기록(검색·클릭·저장 등)',
            '비회원: 검색 문장과 탐색 기록(세션 쿠키 단위)']),
        ('3. 보유 기간', [
            '회원 정보: 탈퇴 시까지', '세션: 30일', '가명 이용 기록: 1년', '0건 검색 문장: 90일',
            '알림 메일 발송 기록: 1년', '관리자 접속·처리 기록: 2년(안전성 확보조치 기준 제8조)',
            '탈퇴 시 상대가 있는 쪽지: 보낸 사람 정보를 지운 채 상대 열람용으로 남김']),
        ('4. 제3자 제공', [
            '학생이 선배에게 쪽지·커피챗을 보내면, 그 선배에게 이름·이메일과 학생이 입력한 프로필이 전달됩니다. 보내기 전에 화면에서 다시 동의를 받습니다.',
            '그 밖에는 법령에 근거가 있는 경우를 제외하고 제3자에게 제공하지 않습니다.']),
        ('5. 처리 위탁과 국외 이전', [
            f'서버·데이터베이스 보관: {values["hosting"]}',
            '알림 메일 발송: 운영자가 설정한 메일 발송 사업자(설정 전에는 발송하지 않음)',
            '국외 이전(제28조의8, 선택 동의자에 한함): 의미 검색 계산 — Google LLC(Kaggle, 미국), '
            'AI 연구 가이드·논문 쉬운 요약 생성 — Anthropic PBC(미국). 이전 항목: 검색 문장, 선택한 수강 과목, 학과·학년. '
            '이전 시기·방법: 요청할 때마다 암호화 통신으로 전송. 거부 방법: 동의 철회(프로필 설정). 거부 시 사전 검색과 기본 가이드만 제공.']),
        ('6. 파기 절차와 방법', [
            '보유 기간이 끝나거나 탈퇴하면 지체 없이 데이터베이스에서 삭제합니다.',
            '백업본은 최대 14일(관리용 서버 사본 30일) 뒤 순차 삭제됩니다.']),
        ('7. 정보주체의 권리와 행사 방법', [
            '프로필 화면에서 열람·정정할 수 있고, 계정 삭제(탈퇴)로 삭제를 요청할 수 있습니다.',
            '처리 정지·동의 철회는 프로필 화면의 설정이나 아래 책임자 연락처로 요청할 수 있으며 10일 이내에 조치합니다.']),
        ('8. 안전성 확보조치(제29조)', [
            '비밀번호 scrypt 단방향 암호화, HTTPS 전송, 세션 토큰 해시 저장',
            '관리 기능은 공개 인터넷에 열지 않고 관리용 서버에서 암호화 터널로만 접근, 관리자 처리 기록 보관',
            '요청 횟수 제한, 매일 백업']),
        ('9. 쿠키', [
            '로그인과 비회원 탐색을 이어가기 위한 세션 쿠키(curri_session)만 씁니다. 광고·추적 쿠키는 쓰지 않습니다.',
            '브라우저 설정에서 쿠키를 거부할 수 있으나 탐색 기록 저장과 로그인이 되지 않습니다.']),
        ('10. 개인정보 보호책임자', [
            f'성명: {v("officer_name")} / 직책: {v("officer_position")}', f'이메일: {v("officer_email")}',
            f'연락처: {v("officer_phone")}']),
        ('11. 권익침해 구제', [
            '개인정보 분쟁조정위원회 1833-6972 (www.kopico.go.kr)', '개인정보 침해신고센터 118 (privacy.kisa.or.kr)',
            '대검찰청 1301, 경찰청 182']),
        ('12. 변경', [f'이 방침은 {v("effective_date")}부터 적용됩니다(버전 {POLICY_VERSION}). 바뀌면 시행 7일 전에 공지합니다.']),
    ]
    return {'title': f'{values["service_name"]} 개인정보 처리방침', 'operator': v('operator'), 'version': POLICY_VERSION,
            'sections': [{'heading': h, 'items': items} for h, items in sections],
            'missing_slots': [SLOT_LABELS[k] for k in SLOT_LABELS if not values.get(k)],
            'notice': '운영자 정보가 비어 있는 항목은 【입력 필요】로 표시됩니다.'}
