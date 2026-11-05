> **레거시 데이터 (2026-10-13 이동)**: 4개 학과 범위의 MVP 데이터다. 기준 데이터는 [data/README.md](../../README.md)의 `final_*` 파일로 바뀌었다.
> 현재 앱(`python3 -m curri`)·도구·테스트는 새 데이터로 옮기기 전까지 이 폴더를 기본 데이터 경로로 읽는다(`--data-dir` 기본값). 파일 내용은 옮기기 전과 같다.
> 아래 본문은 이동 전 `data/README.md` 그대로이며, 본문의 `data/…` 경로는 이제 `data/legacy/mvp-4dept/…`를 뜻한다.

# 3분커리 데이터

연구실 추천에 사용하는 교과목 정보와 연구실 정보다. 두 파일 모두 한 줄에 JSON 객체 하나를 담는 JSONL 형식이며 UTF-8로 저장되어 있다.

## courses.jsonl — 교과목 정보

교과목 **419개 레코드**를 담는다. 사용자가 흥미를 느낀 수업과 수강 경험을 바탕으로 관심 분야와 준비도를 이해하는 데 사용한다.

| 필드 | 설명 |
|---|---|
| `record_id` | 레코드 식별자 |
| `course_code` | 과목 코드. 여러 코드가 함께 표기된 항목도 있음 |
| `course_name_kr`, `course_name_en` | 국문·영문 과목명 |
| `credit_original` | 학점 관련 원문 표기 |
| `description` | 과목 설명 |
| `objectives` | 강의목표 |
| `prerequisites_text` | 선수과목·수강에 필요한 지식에 대한 설명 |
| `course_plan` | 강의 진도계획 |
| `syllabus_source_id`, `syllabus_matched_code` | 연결된 강의계획의 식별 정보. 출처 URL이나 과목 간 동등성을 보장하지 않음 |
| `source` | 수집 자료의 식별 메타데이터. 파일 내용 이해나 추천 입력에 필수는 아님 |
| `quality_flags` | 해석 시 확인해야 할 사항 |

수집 시점·적용 학기·출처 URL은 미확인이다. 최신 개설 여부나 현재 이수요건을 확정하는 자료로 사용하지 않는다.

복합 코드 표기가 20건 있어 한 레코드가 반드시 하나의 독립 과목을 뜻하지는 않는다. 선수사항은 수업의 조건이며 연구실 지원 필수조건이 아니다. 빈 값은 정보 미확보를 뜻한다.

## labs.jsonl — 연구실 정보

교수 기준 연구실 기록 **65건**을 담는다. 연구 관심과의 연결을 살펴보고 추천 이유를 설명하는 데 사용한다. 수집 자료가 있는 60건과 사용 제외 기록 5건으로 구성된다.

| 필드 | 설명 |
|---|---|
| `record_id` | 레코드 식별자 |
| `professor_name` | 교수명 |
| `department` | 소속 학과·분야 |
| `lab_url`, `lab_location` | 연구실 홈페이지와 위치 |
| `collected_at` | 수집 시각. 현재 미확인으로 `null` |
| `sections` | 연구 소개·논문·지원 안내·미분류 본문 중 확보된 항목 |
| `sections.*.text` | 해당 항목의 본문 |
| `sections.*.source_urls` | 본문을 수집한 웹페이지 URL 목록 |
| `sections.*.verification_status` | 항목의 검증 상태 |
| `sources` | 수집 자료의 식별 메타데이터. 파일 내용 이해나 추천 입력에 필수는 아님 |
| `data_status` | `collected`: 수집 자료 있음, `excluded`: 사용 제외 |
| `quality_flags` | 본문 부족·공동 홈페이지 등 품질 표시 |
| `review_notes` | 확인할 사항과 사용 제외 사유 |

**추천 근거 입력은 `data_status == "collected"`인 60건으로 제한한다.** `collected`는 사실 검증 완료나 현재 모집 중임을 뜻하지 않는다. `excluded`인 5건은 접근 실패·빈 본문 등으로 사용할 수 없으며, 재수집할 이유를 기록한다.

수록 범위는 Computer Science 29, Electrical Engineering 29, IT Convergence 6, Semiconductor Engineering 1건이다. 포스텍 전체 연구실을 포괄하지 않는다.

교수 기준 기록이므로 같은 연구실이나 홈페이지를 공유하는 항목이 있다. 후보를 압축할 때 동일 연구실을 중복 제시하지 않도록 확인해야 한다.

연구 소개 부족·미분류 홈페이지·과거 모집 공고 등이 포함되어 있으므로 본문과 품질 표시를 함께 읽는다. 지도 방식·분위기·현재 모집 여부는 명시된 근거 없이 추정하지 않는다. 여러 페이지를 합친 본문은 개별 문장과 URL의 대응이 미확인이다.

## 프로필 초안 (2026-09-16, 검토 전)

원본 두 파일에서 추천에 쓸 구조화 프로필을 뽑은 초안이다. 모두 `review_status: draft` 또는 `auto`이며 사람이 검토하기 전에는 서비스의 사실 근거로 쓰지 않는다.

| 파일 | 내용 | 만든 방법 |
|---|---|---|
| `concepts.json` | 연구실과 과목이 공유하는 개념 어휘 70개(한·영 라벨, 과목 매칭 키워드) | Claude 작성 |
| `lab_profiles.jsonl` | 후보 단위 연구실 58곳의 요약, 주제(개념·도메인/방법 역할·라벨), 근거 인용, 자료 상태 | Claude가 수집 원문을 읽고 작성. 인용 300건은 `tools/build_lab_profiles.py`가 원문과 대조 |
| `course_profiles.jsonl` | 과목 419건의 개념 태그와 근거 발췌 | `tools/build_course_profiles.py`의 키워드 규칙 |
| `goldset.jsonl` | 추천 평가용 관심 문장 25개와 기대 연구실 | Claude 초안 |

`status`는 `ok`(연구 소개 또는 논문 확보), `thin`(제목·구성원 관심사 수준), `insufficient`(본문 없음)이다. 주제의 `weight`는 `primary`/`secondary`(일반 방법 개념은 단독 근거 불가), `scope`는 `core`/`application`(응용 주제는 과목 연결에 쓰지 않음)이다. `evidence_grade`는 근거로 쓴 자료 종류다. 인용문은 원문의 연속 구절이며 요약·라벨·역할은 Claude의 판단이다.
