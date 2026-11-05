# 로컬 MVP 개발 안내

## 실행

Python 3.11 이상에서 실행한다. 앱 실행에는 추가 Python 패키지나 API 키가 필요 없다.

```bash
python3 -m curri
```

주소는 `http://127.0.0.1:8000`이다. Codespaces 포트 전달 등 다른 인터페이스가 필요하면 다음처럼 실행한다.

```bash
python3 -m curri --host 0.0.0.0 --port 8000
```

HTTPS 프록시 뒤에서는 `--secure-cookie`를 추가한다. 이 서버는 로컬 프로토타입 검증용이며 인터넷 운영 배포용 서버가 아니다.

기본 실행은 `data/sunwoo/legacy/mvp-4dept/`의 과목·연구실·프로필을 읽는다. 이 데이터가 없으면 시작 단계에서 안내와 함께 중단한다. `--data-dir`로 다른 호환 데이터 폴더를 지정할 수 있다.

기본 DB는 `.local/curri.sqlite`이며 자동 생성된다. 서비스 데이터 JSONL을 수정하지 않는다. 다른 데이터나 테스트 DB는 `--data-dir`, `--db`로 지정한다.

## 구현된 범위

- 관심·고민과 탐색 목적(탐색/연구참여/진학)을 입력한다. 목적은 기록만 하며 현재 추천 점수에 사용하지 않는다.
- 한국어·영어의 명시적 연구 주제와 수집 본문을 연결해 후보와 원문 구절을 제시한다. 분야명을 몰라도 알려진 과목명·사전 내 표현으로 탐색할 수 있다.
- 관심이 도메인·방법론 모두에 연결되면 함께 표시한다. 단순 동시 출현이 실제 연구 방법의 활용 관계를 입증하지는 않으므로 확인할 점을 설명한다.
- 연구실 하나를 선택하면 연결되는 모든 과목을 제시한다. 검색창으로 좁힐 수 있고 수강 표시 없이도 진행할 수 있다.
- 수강 선택에 따라 활용 가능한 과목, 추가 학습 과목과 원문을 연결한 두 갈래 탐색 가이드를 제공한다.
- 첫 연구실은 비회원으로 끝까지 탐색할 수 있다. 두 번째 다른 연구실은 서버가 로그인으로 제한한다.
- 비회원도 첫 탐색 초안·후보·메모를 저장한다. 로그인 시 계정으로 승계한다. 기존 계정의 같은 연구실 결과와 충돌하면 직전 익명 결과를 사용하고 이전 버전도 보존한다.
- 저장된 후보와 메모를 다시 확인하고 후보에서 뺄 수 있다. 상세에서 수강·메모를 변경하면 짧은 지연 후 초안을 저장한다. 수강을 변경하면 이전 가이드는 무효화한다.
- 연구실을 다시 열 때 저장된 수강 선택 중 현재 연관 과목 목록에 없는 과목은 서버가 해제하고 이전 가이드를 지운다(추천 엔진이나 프로필이 바뀐 뒤 과거 세션을 이어갈 때 필요). 화면에도 해제 개수를 알린다.

## 커뮤니티 기능 (2026-10-01 추가)

계획과 결정 사항: [커뮤니티 확장 계획](plans/2026-10-01-community.md). 구현은 `curri/community.py`.

- **확장 프로필**: 회원가입 시 이름(실명)·별명(화면 표시명, 중복 불가)·이메일·학교·관심 분야(개념 태그 1개 이상 또는 직접 입력)를 받는다. 학과·복수전공·학년·연구참여 목표·희망 시기·한 줄 소개·자기소개는 선택이며 상단의 별명 버튼 → `내 프로필`에서 수정한다. 프로필 이전에 만든 계정은 필수 항목을 채워야 후기·쪽지를 쓸 수 있다.
- **연구참여 후기**: 로그인 + 필수 프로필 + '연구참여를 마쳤어요' 자기 신고로 작성한다. 4개 항목 1~5점과 서술형. 연구실당 1개(수정·삭제 가능). 연구실 상세 하단과 상단 메뉴 `연구참여 후기` 게시판에서 본다. 후기에는 별명·학과·학년만 보인다.
- **대학원생 선배 연락**: 연구실 상세에 정보 공개에 동의한(`contact_consent`) 선배의 이름·과정·연구 분야를 보여주고, 이메일은 로그인 사용자에게만 보인다. 학부생은 웹 안의 쪽지를 보내고, 선배는 `쪽지함`에서 보낸 학생의 프로필(실명·이메일 포함)과 함께 읽고 답장한다. 실제 이메일은 발송하지 않는다. 하루 30건 제한.
- **만남 약속 (2026-11-05)**: 쪽지함 대화 상단의 `만남 약속 잡기`에서 대면/온라인, 20·30분, 후보 시간 1~3개를 제안하고 상대방이 하나를 골라 확정한다. 온라인 확정 시 아래 설정이 있으면 Google Meet 또는 Zoom 링크를 자동 예약하고, 없으면 확정하는 사람이 링크를 붙여 넣는다. 요청·확정·취소는 대화 메시지로 남는다.
- **더미 데이터**: 기본 데이터 폴더의 `community_seed.json`을 서버 시작 시 멱등 삽입한다. 파일과 DB 행에 `dummy` 표시가 있다. 넣지 않으려면 `--no-demo-data`.
- **데모 계정**: 모든 더미 계정의 비밀번호는 `curri-demo-2026`이다. 예) 선배 `minji.kwon@postech.example`(곽수하 연구실), 데모 대화가 있는 선배 `wonna.jung@postech.example`(박부견 연구실).

## 추천 방식과 한계

기본 엔진은 `curri/profile_catalog.py`의 `ProfileCatalog`다. 외부 LLM·임베딩 호출 없이, 사람이 검토하는 **구조화 프로필**을 공유 개념 어휘로 연결하는 규칙 기반 구현이다. 이전 엔진(`curri/catalog.py`, 원문 키워드 매칭)은 `--engine rules`로 남겨 두었고 골드셋 비교의 기준선이다.

기본 입력 데이터는 `data/sunwoo/legacy/mvp-4dept/` 아래의 `concepts.json`, `lab_profiles.jsonl`, `course_profiles.jsonl`이다. 만드는 방법과 검토 상태는 [데이터 설명](../../data/README.md)에 있다.

- **관심 해석**: 관심 문장에서 개념 키워드(`keywords` + 검색 전용 `query_keywords`)를 찾는다. 과목명이 들어 있으면 그 과목의 제목 수준 개념을 더한다. 개념이 하나도 안 잡히면 프로필 요약·라벨·인용에 대한 낱말 검색으로 후퇴한다.
- **연구실 점수**: 일치한 주요 주제마다 1점(AI·기계학습 같은 일반 개념은 0.7), 서로 다른 주제가 여럿이면 가산한다. 근거 등급(연구 소개 1.0, 논문 목록 0.8, 구성원 관심사·연구실명 0.5)과 자료 상태(제목 수준 0.7, 본문 없음 0)를 곱한다. AI·기계학습이 `method` 역할인 연구실에서는 이 주제만으로 후보가 되지 않는다(검토자 규칙).
- **과목 연결**: 연구실의 **핵심** 주제(`scope: core`)와 과목 태그가 겹칠 때만 연결한다. 응용 주제(`scope: application`, 예: 기계학습 연구실의 신약 발굴)는 관심 검색에는 쓰지만 과목을 끌어오지 않는다. 한국어 키워드는 부분 문자열 매칭이라 '분자'가 '고분자'에 걸리는 식의 오탐이 생기므로 짧고 일반적인 낱말은 어휘에서 빼거나 약한 키워드로 둔다. 프로필이 넓은 연구실(주요 개념 4개 이상)에서는 과목명에 개념이 있거나 개념이 둘 이상 겹쳐야 한다. 연구실당 과목 수 중앙값은 13개다.
- **가이드**: 이전과 같은 두 갈래 구조이며 주제 라벨과 근거 인용을 프로필에서 가져온다.

골드셋 25문장(`data/sunwoo/legacy/mvp-4dept/goldset.jsonl`, 초안)에 대한 기존 `tools/eval_goldset.py` 결과는 상위 5개 적중률 0.28→0.81, 재현율 0.55→0.91이다(2026-09-16). 골드셋과 프로필은 검토 전 초안이므로 이 수치는 방향 확인용이다.

한계는 다음과 같다. 프로필과 골드셋 대부분은 Claude 초안이며 9곳만 사람이 판정했다. 어휘 밖 표현은 놓친다. 논문 제목만으로 추정한 연구실 12곳, 자료가 제목 수준인 5곳, 본문이 없는 2곳은 재수집이 필요하다. 가이드는 여전히 공개 자료 탐색·재현 제안이지 실제 진행 중인 프로젝트가 아니다.

## 인증·저장

`curri/store.py`가 SQLite 소유권과 트랜잭션을 담당한다.

- 로컬 이메일·비밀번호 계정이다. 이메일 소유 확인, 비밀번호 복구, 학교 소속 검증은 없다.
- 비밀번호는 사용자별 salt와 scrypt 해시로 저장한다. 세션은 임의 토큰의 해시를 DB에 저장하며 로그인 시 토큰을 회전한다.
- 쿠키는 HttpOnly, SameSite=Lax이며 HTTPS 옵션에서 Secure를 적용한다. 토큰은 브라우저 저장소에 노출하지 않는다.
- 익명·계정 세션 수명은 발급 후 30일이다. 비회원의 첫 연구실 제한은 동일 세션 내에서 유지한다. 쿠키 삭제나 새 브라우저에서 반복 이용을 막는 엄격한 무료 사용량 제한은 아니다.
- 로그인 실패·취소는 첫 탐색을 유지한다. 로그아웃 후에는 새 비회원 세션으로 돌아가며 계정 기록은 남는다.
- API는 클라이언트가 보낸 사용자 ID를 신뢰하지 않고 서버 세션에서 소유자를 결정한다. 최초 연구실 지정은 트랜잭션으로 직렬화해 동시 요청도 한 연구실만 허용한다.
- JSON 요청 크기, 문자열 길이, 과목 소속을 검사하고 교차 출처 변경 요청을 차단한다. 비밀번호 시도는 IP 기준 5분 15회로 제한한다.

실제 운영 배포 전에는 운영용 서버·HTTPS, 검증된 인증 수단과 계정 복구, 만료 데이터 정리·보관 정책, 모니터링, 프록시 환경·부하·보안 검토가 필요하다. 결제는 구현하지 않았다.

### 온라인 만남 링크 설정

`.local/meeting_links.json`(또는 `--meeting-links-config` 경로)에 하나만 둔다. 파일이 없으면 링크 직접 입력 방식으로 동작한다. 자격 증명이므로 저장소에 커밋하지 않는다(`.local/`은 git 제외).

Google Meet: Google Cloud 프로젝트에서 Calendar API를 켜고 OAuth 클라이언트를 만든 뒤, 서비스 운영용 Google 계정으로 `https://www.googleapis.com/auth/calendar.events` 범위 동의를 받아 갱신 토큰을 얻는다. 일정은 그 계정 캘린더에 만들어지고 두 사람의 계정 이메일이 참석자로 들어간다. 초대된 이메일의 Google 계정으로 로그인해야 승인 없이 입장한다. OAuth 동의 화면이 '테스트' 상태면 갱신 토큰이 7일 뒤 만료되므로 '프로덕션'으로 게시한 뒤 토큰을 받는다.

```json
{"provider": "google", "client_id": "…", "client_secret": "…", "refresh_token": "…", "calendar_id": "primary", "send_invites": false}
```

Zoom: Zoom Marketplace에서 Server-to-Server OAuth 앱을 만들고 `meeting:write:meeting:admin`(또는 `meeting:write:admin`)·`meeting:delete:meeting:admin` 범위를 준다. 호스트 없이도 입장하도록 예약한다.

```json
{"provider": "zoom", "account_id": "…", "client_id": "…", "client_secret": "…", "user_id": "me"}
```

`send_invites: true`면 Google이 참석자에게 초대 메일을 보낸다. 더미 계정 이메일로도 발송되므로 실제 사용자만 있는 환경에서 켠다.

## API

| 경로 | 역할 |
|---|---|
| `GET /api/session` | 세션 생성/확인과 사용자 소유 탐색 복원 |
| `POST /api/search` | `{interests, goal}` 저장 및 후보 검색 |
| `POST /api/explore` | `{lab_id}`의 상세 탐색 권한 확인 및 과목 제공 |
| `POST /api/guide` | `{lab_id, selected_ids}`로 가이드 작성·저장 |
| `POST /api/save` | `{lab_id, selected_ids, note, saved}` 초안·후보 저장 |
| `POST /api/register` | `{email, password, account}` 필수 프로필과 함께 계정 생성 및 익명 탐색 승계 |
| `POST /api/login` | `{email, password}` 로그인 및 익명 탐색 승계 |
| `POST /api/logout` | 현재 세션 종료 및 새 익명 세션 발급 |
| `GET /api/concepts` | 관심 분야 태그 후보 |
| `POST /api/account` | 내 프로필 수정 |
| `GET /api/community?lab_id=` | 연구실 후기 요약·목록, 선배 목록(이메일은 로그인 시) |
| `GET /api/reviews` | 전체 후기 게시판 |
| `POST /api/review`, `POST /api/review/delete` | `{lab_id, completed, term, duration, activity, ratings, good, improve, recommend_for}` 후기 작성·수정 / 삭제 |
| `POST /api/contact` | `{graduate_id, subject, body}` 선배에게 쪽지 |
| `GET /api/inbox`, `GET /api/thread?id=`, `POST /api/reply` | 쪽지함, 대화 보기(읽음 처리·만남 약속 포함), `{thread_id, body}` 답장 |
| `POST /api/meeting/request` | `{thread_id, mode: online/offline, minutes: 20/30, slots: ["YYYY-MM-DDTHH:MM"(한국 시간)], place, note}` 만남 제안 |
| `POST /api/meeting/confirm` | `{meeting_id, start(초 단위 시각), join_url?}` 상대방이 확정. 링크 생성 실패는 502 `meeting_link_failed` |
| `POST /api/meeting/cancel` | `{meeting_id}` 요청 철회·거절·확정 취소 |

두 번째 비회원 상세 요청은 401과 `code: login_required`, 잘못된 인증은 401과 `invalid_credentials`, 필수 프로필 미완성은 403과 `profile_required`를 반환한다. 내가 참여하지 않은 쪽지 대화는 404다. 검증 오류는 400, 없는 연구실은 404다. API 응답에는 연구실 자료의 로컬 원본 경로나 전체 과목 파일을 노출하지 않는다.

## 테스트

```bash
python3 -m unittest discover -s tests -v
node --check curri/static/app.js
python3 tools/eval_goldset.py
```

프로필 엔진 테스트(`tests/test_profile_catalog.py`)는 반입한 MVP 데이터를 쓴다. 프로필을 고친다면 해당 데이터 경로에서 인용을 다시 대조해야 한다.

`node --check`는 문법만 확인한다. 브라우저 전역 이름(`top`, `name`, `parent` 등)과 충돌하는 전역 함수 선언처럼 Node에서는 통과하고 브라우저에서만 실패하는 문제는 잡지 못하므로, 화면 코드를 바꾸면 아래 브라우저 검증을 함께 실행한다.

실제 HTTP 서버 테스트는 로컬 소켓 실행 권한이 필요하다. 단위·HTTP 테스트는 임시 DB와 작은 명시적 데이터를 사용하며 사용자 DB를 변경하지 않는다.

선택적 브라우저 검증은 Node.js와 Playwright가 필요하다. 테스트 계정을 만들기 때문에 별도 DB로 앱을 실행한다.

```bash
python3 -m curri --port 8001 --db /tmp/curri-browser-test.sqlite
# 별도 터미널: Playwright가 설치된 환경에서 실행
CURRI_URL=http://127.0.0.1:8001 node tests/browser.cjs
```

Codespaces처럼 Chromium 시스템 라이브러리가 없는 환경에서는 먼저 다음을 한 번 실행한다. 브라우저가 열리지 못하면 `Target page, context or browser has been closed` 오류가 난다.

```bash
npm exec --yes --package=@playwright/test -- playwright install-deps chromium
npm exec --yes --package=@playwright/test -- playwright install chromium
```

Playwright가 프로젝트 외부에 설치되어 있다면 `PLAYWRIGHT_MODULE`에 해당 모듈의 절대 경로를 지정할 수 있다. 브라우저 스크립트는 데스크톱·모바일 흐름, 저장·새로고침, 로그인 전환과 입력 경합을 검증하고 `/tmp/curri-screenshots/`에 화면을 저장한다.

## 다음 개발의 초점

우선순위와 완료 기준은 [제품 기준 9절의 다음 개발 계획](PRODUCT_PLAN.md#다음-개발-계획-2026-09-16-작성)을 따른다. 당장은 팀 공유 문서, 골드셋 판정, 자료가 부족한 연구실 재수집 순이다. 검색·가이드를 교체할 때는 `ProfileCatalog`의 인터페이스를 유지하고 `tools/eval_goldset.py`로 전후를 비교한다.

프로필 검토 페이지: https://claude.ai/artifact/FuBiPCfHXfUgPARhivuY8b (조직 내부 공유, 판정은 페이지의 DB에 저장되며 `data/profile_reviews.json`에 스냅샷을 남긴다).
