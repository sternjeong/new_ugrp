# 3분커리 데이터

포스텍 전체 교과목·연구실을 크롤링해 만든 **기준 데이터**의 계약서다. 각 파일의 단위, 필드의 의미·타입·허용값, 파일 사이의 연결, 지켜야 할 무결성 규칙을 정의한다. 데이터 검증은 이 문서를 기준으로 한다.

- 기준일: 2026-10-26
- 상태: **연구실은 사람 검증과 정제본까지 끝났고(`labs.jsonl`, 4.11), 교과목은 `필수` 규칙을 지키며 `확인` 항목을 정해 정제본을 만들었다(`courses.jsonl`, 3.6). 연구실 대표 논문은 `papers.jsonl`(4.12)이다. 연구센터는 검증 전이다.** 아래 규칙의 "관측" 값은 가져온 원본을 그대로 측정한 기준선이다(2026-10-13). 원본은 9절에 적은 예외 말고는 고치지 않는다(G-05).
- 현재 앱(`python3 -m curri`)은 정제본 `labs.jsonl`·`courses.jsonl`·`papers.jsonl`에서 만든 `app_profiles.jsonl`과 BGE-M3 임베딩 연결표를 읽는다. [`legacy/mvp-4dept/`](legacy/mvp-4dept/README.md)는 서비스 추천에 사용하지 않는다.

### 이 문서를 읽는 법
- **필드 표**: `필수`는 값이 반드시 있어야 하는지(결측 불가), `결측 표기`는 값이 없을 때 쓰는 표현이다. `관측`은 2026-10-13 원본에서 센 값이다.
- **규칙 ID**: `C-`는 교과목, `L-`은 지도교수·연구실, `R-`은 연구센터, `X-`는 파일 간 규칙이다. 검증 결과를 기록할 때 이 ID를 쓴다.
- **규칙 등급**: `필수`는 어기면 데이터를 쓸 수 없다. `권장`은 품질 문제로, 쓰임새에 따라 고칠지 정한다. `확인`은 규칙을 정하기 전에 사람이 판단해야 하는 항목이다.
- **해석**: 출처 문서에 정의가 없어 값을 보고 추론한 의미에는 "(해석)"을 붙였다. 검증 때 확인하고 확정한다.

---

## 1. 파일 목록

| 파일 | 단위(1줄 = ) | 레코드 | 크기 | 역할 |
|---|---|---|---|---|
| `final_courses.jsonl` | 학수번호 1개 | 1,316 | 3.9 MB | 교과목과 강의계획서 |
| `final_labs.jsonl` | 지도교수 1명 + 소속 연구실 (교수 미확인 연구실 포함) | 365 | 16.3 MB | 연구실·교수·논문 |
| `research_centers.jsonl` | 연구센터·연구단·연구소 1곳 | 29 | 48 KB | 지도교수 레코드가 아닌 연구 조직 |
| `courses.jsonl` | 학수번호 1개(정제본) | 1,316 | 3.4 MB | `final_courses.jsonl`에 2026-10-26 결정(C-09·C-11·C-13·X-03·X-04)을 적용한 결과. 과목 데이터를 쓸 때는 이 파일을 읽는다(3.6) |
| `papers.jsonl` | 연구실 1곳(추천 가능 307곳) | 307 | 5.3 MB | 연구실마다 본인 논문 최대 10편과 선정 이유·초록(4.12). 원본 `representative_papers`를 대신한다 |
| `labs.jsonl` | 교수·연구실 기록 1건(정제본) | 365 | 2.7 MB | `final_labs.jsonl`과 사람 검증(`curation/advisors.jsonl`)을 합쳐 형식을 통일한 결과. 연구실 데이터를 쓸 때는 이 파일을 읽는다(4.11) |
| `legacy/mvp-4dept/` | — | — | — | 4개 학과 MVP 데이터. 현재 앱이 읽는다([레거시 안내](legacy/mvp-4dept/README.md)) |

### 1.1 출처
세 파일은 `feat/vectorRAG` 브랜치 커밋 `d358143`(2026-10-12, 원래 `vector-rag-chroma` 브랜치 `0e98cd2`의 스냅샷)의 `data/processed/`에서 **수정 없이** 가져왔다. 그 뒤 원본을 고친 것은 G-05의 예외로 허용한 한 번뿐이다(2026-10-25 학과 이름, 9절). 아래 해시는 지금 파일의 값이고, 가져올 때 값은 괄호에 둔다.

| 파일 | SHA-256 앞 16자 | 만든 스크립트(feat/vectorRAG) |
|---|---|---|
| `final_courses.jsonl` | `fff3ce7aa405d0c7` (가져올 때 `ea0264ead2b7760f`) | `preprocessing/preprocess.py` |
| `final_labs.jsonl` | `d5ffab8a5c37856d` (가져올 때 `d8aaec626071062d`) | `preprocessing/build_advisors.py` |
| `research_centers.jsonl` | `d5d4c22339f0b960` | `preprocessing/build_advisors.py` |

이 브랜치에는 생성 스크립트와 중간 산출물(크롤링 원본, LLM 추출 결과, 논문 선정 근거)이 없다. 다시 만들거나 원본을 추적해야 하면 `feat/vectorRAG` 브랜치의 `CLAUDE.md`와 `preprocessing/`을 본다. 무결성을 확인하려면 `sha256sum data/*.jsonl`로 위 값과 비교한다. 구조도 검사(`python3 tools/build_repo_map.py --check`, 커밋 전 훅)가 이 표의 첫 해시와 실제 파일을 대조해, 기록 없이 원본이 바뀌면 커밋을 막는다.

### 1.2 수집 과정 요약
- **교과목**: POVIS 강의계획서를 2025-1, 2025-2, 2026-1, 2026-2 네 학기에 걸쳐 학과별로 크롤링했다. 같은 학수번호가 여러 학기에 있으면 **가장 최근 학기 1건만** 남겼다. 여름·겨울학기는 수집하지 않았다.
- **연구실·교수**: 수집 출처는 학과 소개 페이지의 연구실 목록, 대학 연구자 검색(교수 302명), 연구실 사이트 390곳이다. **대학 연구자 검색**은 POSTECH 공식 홈페이지의 "연구·산학 > 연구자 검색" 페이지(`https://postech.ac.kr/kor/research-industry-academia/researcher-search.do`)다. 교수마다 이름·직위·학과·이메일·홈페이지·학력·경력과 학술지·학술회의 논문 전체 목록(제목·학술지·연도)이 있다. `feat/vectorRAG`의 `preprocessing/crawl_researchers.py`가 2026-10-09에 302명을 모두 받았고, 이 문서와 사례집에서 "연구자 검색"·"연구자 DB"·"학교 목록"은 모두 이 페이지를 말한다. 페이지에 논문을 채우는 학내 시스템이 무엇인지는 확인하지 않았다. 연구실 사이트에서 연구소개·논문·지원안내를 추출했다. 로컬 LLM으로 연구실 이름·교수·키워드를 보충하고, OpenAlex·PubMed·arXiv·Crossref로 대표 논문과 초록을 모았다. 그다음 교수 단위로 합쳤다.
- **수집 시각**: 레코드별 수집 시각 필드는 없다. 교과목은 위 네 학기 기준이다. 연구실 쪽 생성 스크립트에는 2026-10-09 ~ 10-10의 결정 기록이 있고, 스냅샷 커밋은 2026-10-12다. 연구실 사이트를 크롤링한 날짜는 기록되지 않았다.

---

## 2. 공통 규칙

| ID | 등급 | 규칙 | 관측 |
|---|---|---|---|
| G-01 | 필수 | UTF-8, JSON Lines(한 줄에 JSON 객체 하나), 빈 줄 없음 | 세 파일 모두 만족 |
| G-02 | 필수 | 한 파일의 모든 레코드는 같은 키 집합·같은 순서를 가진다 | 만족 |
| G-03 | 권장 | 결측 표기를 파일 안에서 하나로 통일한다 | 교과목은 빈 문자열 `""`, 연구실은 `null`·빈 배열 `[]`. 파일마다 다르다 |
| G-04 | 권장 | 본문 줄바꿈은 `\n`만 쓴다 | 교과목 본문 596건에 `\r\n`이 섞여 있다 |
| G-05 | 필수 | 원본 파일은 가져온 그대로 둔다. 고칠 때는 정제 스크립트와 결과 파일을 새로 만들고 이 문서의 9절에 기록한다. **예외:** 원본 값이 잘못 들어간 것이 확실하고 사용자가 허용하면, 바로잡는 목적으로만 원본을 고친다. 바꾼 필드·건수·이유를 9절에, 새 해시를 1.1절에 적는다(사례집 E-14) | 예외 1건: 2026-10-25 학과 이름 `인문사회과학부` → `인문사회학부`(사례집 A-14) |
| G-06 | 확인 | 개인 연락처(교수 이메일, 강의계획서의 조교 이메일·전화번호)를 화면에 노출할 범위를 정한다 | 교수 이메일 302건, 강의계획서 연락처: 이메일 34건·전화번호 29건 |

---

## 3. `final_courses.jsonl` — 교과목

### 3.1 단위와 키
- 1 레코드 = 학수번호 1개. **키는 `course_code`이며 유일하다.**
- 같은 과목이 여러 학기에 열렸으면 최신 학기의 강의계획서·담당교수만 있다. 다른 학기의 담당교수나 계획서 차이는 남아 있지 않다.
- 학부·대학원 과목을 함께 담는다. 학수번호 숫자 첫 자리가 1–4면 학부, 5–9면 대학원 과목이다(해석): 학부 601, 대학원 715.

### 3.2 필드

원천 열의 `ZSIL_TYPE_*`는 POVIS 강의계획서 항목 코드다. 1000=강의목표, 1100=선수·수강필수사항, 1200=성적평가, 1300=참고문헌, 1400=강의진도계획, 1500=수업운영, 1600=학습법·기타.

| 필드 | 타입 | 필수 | 결측 표기 | 의미 | 원천 | 형식·허용값 | 관측(값 있음) |
|---|---|---|---|---|---|---|---|
| `course_code` | string | 예 | — | 학수번호 | `GS_SUBJECT.SM_SHORT` | `^[A-Z]{4,6}\d{3}(\d{2}\|[A-Z]{1,2})?$` (3.3 참고) | 1,316 |
| `course_title` | string | 예 | — | 과목명(국문 우선) | `SM_STEXT` | 공백 포함 자유 형식 | 1,316 (영문만 52) |
| `credit` | string | 예 | — | 학점 표기 | `ZCREDIT` | `^\d+-\d+-\d+$`, `강의-실습-학점`(해석). 예 `3-0-3`, `0-2-1` | 1,316 |
| `category` | string | 예 | — | 이수 구분 | `CATEGORYT` | 3.4의 8개 값 | 1,316 |
| `professor` | string | 아니오 | `""` | 최신 학기 담당교수 1명 | `ENAME` | 한글 이름 또는 영문 전체 이름. 여러 명은 담지 않는다 | 1,155 |
| `description` | string | 아니오 | `""` | 강의목표 | `ZSIL_TYPE_1000` | 자유 형식(국·영문) | 1,281 |
| `Lesson Objectives` | string | 아니오 | `""` | 강의목표. **각 레코드 안에서 `description`과 같은 값이다**(같은 원천을 복사한 중복 필드) | `ZSIL_TYPE_1000` | — | 1,281 (1,316건 모두 자기 레코드의 `description`과 같음) |
| `prerequisites` | string | 아니오 | `""` | 선수과목·수강 필수사항 | `PREREQUISITE`, 비면 `ZSIL_TYPE_1100` | 자유 형식. 학수번호 목록이 아니다 | 1,015 |
| `Lecture progress plan` | string | 아니오 | `""` | 주차별 강의 진도 | `ZSIL_TYPE_1400` | 자유 형식 | 1,109 |
| `grading` | string | 아니오 | `""` | 성적 평가 방법 | `ZSIL_TYPE_1200` | 자유 형식 | 1,096 |
| `textbooks` | string | 아니오 | `""` | 교재 목록 | `GT_ZCMT457` | `제목 (저자)`를 `; `로 이은 한 줄 | 540 |
| `references` | string | 아니오 | `""` | 참고문헌·자료 | `ZSIL_TYPE_1300` | 자유 형식 | 890 |
| `course_operation` | string | 아니오 | `""` | 수업 운영 방식(조교 연락처 포함 가능) | `ZSIL_TYPE_1500` | 자유 형식 | 880 |
| `other_info` | string | 아니오 | `""` | 학습법·기타 안내 | `ZSIL_TYPE_1600` | 자유 형식 | 471 |
| `_dept` | string | 예 | — | 개설 학과(크롤링 때 고른 학과) | 크롤러 메타 | 3.4의 27개 값 | 1,316 |
| `_semester` | string | 예 | — | 남긴 강의계획서의 학기 | 크롤러 메타 | `YYYY CCC`. `090`=1학기, `092`=2학기 (`091` 여름·`093` 겨울은 수집 안 함) | 1,316 |

필드 이름 규칙이 섞여 있다. 대부분은 snake_case지만 `Lesson Objectives`·`Lecture progress plan`은 공백과 대문자를 쓰고, 크롤러 메타는 `_`로 시작한다.

### 3.3 학수번호 형식
- 접미가 없는 형식(영문 4–6자 + 숫자 3자, 예: `CSED101`)이 902건이다.
- 접미 영문 1–2자(예: `EECE490A`, `CSED499II`)는 같은 번호의 분반·주제가 다른 과목이다(해석). 307건.
- 접미 숫자 2자(예: `CSED69901`)는 연구 과목 번호다(해석). 107건.
- 영문 6자 접두(`WICMEF406`, `WIHUMN429A` 등)는 `WI` + 기존 학과 접두로 보인다(해석). 19건.
- 학과 접두는 52종이다. 많은 순: EECE 107, CSED 98, PHYS 73, CHEB 72, MATH 69, MECH 68, AMSE 67, LIFE 64.

### 3.4 값 분포 (관측)
- `_semester`: `2026 092` 549, `2026 090` 396, `2025 090` 207, `2025 092` 164
- `category`: 전공선택 770, 전공필수 203, 연구과목 146, 인문사회과학선택 94, 기초선택 34, 자유선택 27, 교양필수 26, 기초필수 16
- `_dept` 27개: 인문사회과학부 123, 전자전기공학과 122, 융합대학원 113, 컴퓨터공학과 98, 물리학과 73, 화학공학과 72, 수학과 69, 기계공학과 68, 신소재공학과 67, 산업경영공학과 64, 생명과학과 64, 화학과 51, 인공지능대학원 50, 반도체공학과 38, IT융합공학과 33, 배터리공학과 31, 반도체대학원 30, 친환경소재학과 29, 첨단원자력공학부 28, 환경공학부 22, 의공학과 21, 시스템생명공학부 19, 교육혁신센터 16, 첨단재료과학부 5, 포스텍-삼성전자 반도체 교육프로그램 4, 무은재학부 3, 스포츠 AIX 융복합 대학원 프로그램 3
- `credit` 상위: `3-0-3` 848, `1-0-1` 81, `0-2-1` 52, `3-1-3` 46, `2-0-2` 40. `0-0-0` 19건.
- 본문 언어: `description`에 한글이 없는 레코드 677건(영문 강의계획서)

### 3.5 무결성 규칙

| ID | 등급 | 규칙 | 관측 |
|---|---|---|---|
| C-01 | 필수 | `course_code`는 유일하다 | 중복 0 |
| C-02 | 필수 | `course_code`가 3.2의 정규식에 맞는다 | 위반 0 |
| C-03 | 필수 | `course_title`, `credit`, `category`, `_dept`, `_semester`는 비어 있지 않다 | 위반 0 |
| C-04 | 필수 | `credit`은 `숫자-숫자-숫자` 형식이다 | 위반 0 |
| C-05 | 필수 | `category`, `_dept`, `_semester`는 3.4의 값 중 하나다(새 값이 생기면 이 문서에 먼저 추가한다) | 위반 0 |
| C-06 | 권장 | 각 레코드 안에서 `description`과 `Lesson Objectives`가 같은 값이므로 하나로 합친다. 과목 사이에는 값이 다르다 | 1,316건 모두 레코드 안에서 같음 (`description` 값은 950종류) |
| C-07 | 권장 | 강의목표(`description`)가 의미 있는 내용이다. 30자 미만이나 `.` 같은 자리표시 값은 결측으로 본다 | 30자 미만 23건(`.` 포함), 빈 값 35건 |
| C-08 | 권장 | 추천 근거로 쓸 과목은 `description`·`Lecture progress plan` 중 하나 이상에 내용이 있다 | 둘 다 빈 과목 32건 |
| C-09 | 확인 | 학점 `0-0-0` 과목(19건)과 연구과목(146건)을 추천 대상에 넣을지 정한다 | **결정(2026-10-26): 추천에서 뺀다.** 정제본에 남기고 `recommendable=false`, `exclusion`에 `zero_credit`·`research_course` |
| C-10 | 확인 | 과목명이 같은데 학수번호가 다른 경우를 같은 과목으로 볼지 정한다 | 같은 과목명이 2건 이상인 이름 140개(연구과목·분반 다수) |
| C-11 | 확인 | `professor`가 빈 과목(161건)을 어떻게 표시할지 정한다 | **결정(2026-10-26): "담당교수 미정"으로 표시한다**(정제본 `professor_display`) |
| C-12 | 권장 | `prerequisites`에서 학수번호를 뽑아 선수관계로 쓸 경우, 뽑은 학수번호가 C-01의 키 집합에 있는지 확인한다 | 미실시 |
| C-13 | 확인 | `course_operation`·`other_info`에 있는 조교 이메일·전화번호를 화면에서 가린다(G-06) | **결정(2026-10-26): 가린다.** 정제본은 강의계획서 모든 칸에서 이메일(41개 과목)·전화번호(32개 과목)와 온라인 수업 접속 정보(Zoom 링크·회의 ID·암호, 21개 과목)를 `[이메일 가림]` 등으로 바꾼다. 원본은 그대로 |


### 3.6 정제본 `courses.jsonl`

`tools/build_courses.py`가 `final_courses.jsonl`(원본), `curation/departments.json`(학과 대응표, X-04), `labs.jsonl`(연구실 정제본)을 읽어 만든다. `python3 tools/build_courses.py --check`로 최신인지 확인한다. 1줄 = 학수번호 1개, 1,316개 모두 담는다. 모든 레코드가 같은 키를 같은 순서로 가진다(G-02).

| 필드 | 타입 | 의미 |
|---|---|---|
| `code`, `title`, `credit`, `category`, `semester` | string | 원본의 `course_code`, `course_title`, `credit`, `category`, `_semester` |
| `department` | object | `name`(원본 `_dept`), `unit`(대응표의 이름: 연구실 데이터의 학과 이름과 같다), `kind`(`department` · `program`) |
| `recommendable` | bool | 추천에 써도 되는지. 학점 `0-0-0`과 연구과목은 false(C-09, 1,151개가 true) |
| `exclusion` | array | `zero_credit` · `research_course` |
| `professor_display` | string | 화면에 보일 담당교수. 비어 있으면 `담당교수 미정`(C-11, 161개) |
| `professors` | array | 담당교수마다 `{name, lab_id, basis}`. `lab_id`는 `labs.jsonl`의 `id`. `basis`: `name_and_department` · `name_only_unique`(겸임·다른 학과 과목, 같은 이름의 교수가 한 명뿐) · `namesake_unresolved` · `not_in_lab_data`(X-03). 엄격하게 쓰려면 `name_and_department`만 쓴다 |
| `description` | string\|null | 강의목표. 원본의 같은 두 칸(`description`·`Lesson Objectives`)을 하나로(C-06). 글자 없는 자리표시 값은 null(C-07, 36개) |
| `prerequisites`, `lecture_plan`, `grading`, `textbooks`, `references`, `course_operation`, `other_info` | string\|null | 강의계획서 본문. 줄바꿈 `\n`(G-04). 이메일·전화번호·온라인 수업 접속 정보는 가린다(C-13) |
| `masked` | object | 이 과목에서 가린 개수 `{email, phone, access}` |
---

## 4. `final_labs.jsonl` — 지도교수·연구실

### 4.1 단위와 키
- 기본 단위는 **지도교수 1명 = 1레코드**다. 한 교수가 여러 URL(연구실 사이트, 개인 홈페이지, 학과 목록)에 걸쳐 있으면 하나로 합치고 URL은 `urls`에 모두 남긴다.
- 한 연구실에 교수가 여럿이면 교수별로 레코드를 두고 `lab_group`·`lab_mates`로 묶는다. 예: 컴퓨터비전 연구실의 조민수·곽수하 교수.
- **키는 `advisor_id`이며 유일하다.** 형식은 세 가지이고, 레코드의 성격이 다르다.

| `advisor_id` 형식 | 뜻 | 레코드 수 | `professor` |
|---|---|---|---|
| 32자리 16진수 | 대학 연구자 검색에 있는 교수. 값은 `professor.researcher_id`와 같다 | 302 | 객체 |
| `name:<이름>` | 연구자 검색에 없는 교수. 학과 목록이나 사이트에서만 확인됐다(퇴임·이직 추정) | 11 | 객체(`researcher_id`=null) |
| `lab:<lab_id>` | **교수를 확인하지 못한 연구실.** 지도교수 레코드가 아니다 | 52 | `null` |

- 연구자 검색에는 있지만 연결된 연구실 사이트가 없는 교수도 레코드가 있다(`has_lab_site=false`). 16진수 id 중 70건이다.
- 연구센터·연구단·연구소는 이 파일에 없다. `research_centers.jsonl`에 따로 있다.

### 4.2 최상위 필드

| 필드 | 타입 | 필수 | 결측 표기 | 의미 | 형식·허용값 | 관측(값 있음) |
|---|---|---|---|---|---|---|
| `advisor_id` | string | 예 | — | 레코드 키 | 4.1의 세 형식 | 365 |
| `display_name` | string | 예 | — | 화면 표시명 | `<연구실 이름> <교수> 교수` / 이름 없으면 `<교수> 교수 연구실` / 교수 없으면 `<연구실 이름>`. 표시명이 같아지면 끝에 `(학과)`를 붙인다 | 365 (유일) |
| `professor` | object | 아니오 | `null` | 지도교수 정보(4.3) | — | 313 |
| `lab_name` | string | 아니오 | `null` | 연구실 이름 | 출처 우선순위: 학과 페이지 > 사이트 한국어 이름(LLM) > 사이트 영어 이름(LLM) | 286 |
| `lab_name_en` | string | 아니오 | `null` | 연구실 영문 이름 | ASCII만 | 100 |
| `name_source` | string | 아니오 | `null` | `lab_name`의 출처 | `dept_page`(232) · `site_llm`(54) | 286 |
| `lab_url` | string | 아니오 | `null` | 대표 URL. `urls[0].url`과 같다 | URL | 321 |
| `urls` | array | 예 | `[]` | 이 교수에 연결된 모든 URL(4.4) | 대표 URL이 첫 번째 | 비어 있지 않음 321 |
| `research_intro` | string | 아니오 | `null` | 연구실 사이트의 연구소개 본문(크롤링 원문 정리본) | 자유 형식. 메뉴 등 사이트 잔여 문구가 섞일 수 있다 | 267 |
| `admission` | string | 아니오 | `null` | 사이트의 지원·모집 안내 본문 | 자유 형식. **현재 모집 여부를 뜻하지 않는다** | 56 |
| `keywords` | array\<string\> | 아니오 | `null` | 연구 키워드 최대 8개 | 사이트에 명시된 키워드 우선, 없으면 LLM이 연구소개·지원안내에서 추출. 대소문자 무시 중복 없음 | 267 |
| `site_papers` | array | 예 | `[]` | 연구실 사이트의 논문 목록(4.5) | — | 비어 있지 않음 206 |
| `departments` | array\<string\> | 예 | — | 소속 학과·전공. 첫 값이 대표 학과 | 1–3개 | 365 |
| `has_lab_site` | bool | 예 | — | 정상 크롤링된 연구실 사이트가 있는지(`urls` 중 `status=ok`가 있는지) | — | true 278 |
| `lab_group` | string | 아니오 | `null` | 대표 URL의 `lab_id`. 같은 값을 공유하면 같은 연구실 | — | 315 (공유 그룹 3개) |
| `centers` | array\<string\> | 예 | `[]` | 소속 연구센터 이름 | `research_centers.name` 값 | 비어 있지 않음 11 |
| `professor_papers` | array | 예 | `[]` | 대학 연구자 검색의 교수 논문 전체 목록(4.6) | — | 비어 있지 않음 286, 총 32,927편 |
| `lab_mates` | array\<string\> | 예 | `[]` | 같은 `lab_group`의 다른 교수 이름 | 교수 이름 | 비어 있지 않음 6 |
| `representative_papers` | array | 예 | `[]` | 대표 논문 최대 10편(4.7) | — | 비어 있지 않음 278, 총 2,449편 |
| `selection_meta` | object | 아니오 | `null` | 대표 논문 선정 메타(4.8) | — | 313 |

### 4.3 `professor` 객체

| 필드 | 타입 | 필수 | 의미 | 형식·허용값 | 관측 |
|---|---|---|---|---|---|
| `name` | string\|null | 아니오 | 한글 이름 | 한글. 영문 이름만 확인된 교수는 null | 309 (null 4: `name:` 레코드) |
| `name_en` | string\|null | 아니오 | 영문 이름 | 사이트·학과 목록에서 확인한 값만 있다 | 78 |
| `position` | string\|null | 아니오 | 직위 | `교수`·`부교수`·`조교수` | 302 (null 11 = `name:` 레코드) |
| `department` | string | 예 | 연구자 검색의 소속 학과 | `departments[0]`과 같다 | 313 |
| `email` | string\|null | 아니오 | 이메일 | `@postech.ac.kr` | 302 |
| `researcher_id` | string\|null | 아니오 | 연구자 검색 id | 32자리 16진수 | 302 |
| `in_researcher_db` | bool | 예 | 연구자 검색에 있는지 | `researcher_id`가 있으면 true | true 302 |
| `match` | array\<string\> | 예 | 교수와 연구실을 연결한 근거(여러 개 가능) | 아래 표 | 빈 배열 50(연구실 사이트가 없는 교수) |

`match` 값의 뜻(생성 스크립트 `build_lab_master.py`, `build_advisors.py` 기준). 위에서 아래로 갈수록 근거가 약하다.

| 값 | 근거 | 관측 |
|---|---|---|
| `listed` | 학과 소개 페이지 또는 EECS 수작업 목록에 이 교수의 연구실로 올라 있다 | 136 |
| `listed_not_in_researcher_db` | 목록에는 있으나 연구자 검색에 없다 | 6 |
| `homepage_url` | 연구자 검색의 홈페이지 URL이 연구실 URL과 같다 | 99 |
| `homepage_host` | 홈페이지와 연구실 사이트의 호스트가 같다 | 9 |
| `homepage_subpath` | 교수 홈페이지가 연구실 사이트의 하위 경로다 | 3 |
| `subpath_of_lab_site` | 교수 URL이 다른 연구실 사이트의 하위 경로라서 그 연구실에 붙였다 | 4 |
| `email_in_site` | 연구실 사이트 본문에 교수 이메일이 있다 | 11 |
| `name_in_site` | 사이트 본문에 "이름 교수/Professor"가 있다 | 5 |
| `site_llm_en_romanized` | LLM이 사이트에서 뽑은 영문 이름을 한글 이름의 로마자 표기와 맞췄다 | 11 |
| `site_llm_not_in_researcher_db` | LLM이 사이트에서 뽑은 이름이 연구자 검색에 없다 | 5 |
| `name_in_site_weak` | 학과가 맞고 본문 앞부분에 이름만 있다(약한 근거) | 2 |

### 4.4 `urls[]` 항목

| 필드 | 타입 | 의미 | 허용값 | 관측 |
|---|---|---|---|---|
| `url` | string | 연구실·교수 페이지 URL | URL | 365 |
| `lab_id` | string\|null | 정규화한 URL(스킴·`www` 제거 등). 크롤링 단위 식별자 | — | null 6(`not_crawled`) |
| `status` | string | 크롤링 결과 | `ok` 정상, `needs_review` 접근 실패·무관한 본문, `not_crawled` 학과 공용 사이트이거나 홈페이지 미등록 | ok 317, needs_review 42, not_crawled 6 |
| `review_reason` | string\|null | `ok`가 아닌 이유 | 자유 형식 | 48 (접근 실패 22, 에러 페이지 9, 무관한 본문 9, 미등록 6 등) |

### 4.5 `site_papers[]` 항목 — 연구실 사이트의 논문 목록
`title`(string), `year`(int), `venue`(**항상 null**), `doi`(**항상 null**), `abstract`·`abstract_source`·`arxiv_id`·`arxiv_url`(EECS 일부 연구실만, 123편). 총 2,041편이다. 제목·연도는 로컬 LLM이 사이트 원문에서 뽑았다.

### 4.6 `professor_papers[]` 항목 — 연구자 검색의 논문 목록
`title`, `year`(int), `venue`(string|null), `doi`(**항상 null**), `section`, `abstract` 외 3개(53편만). `section` 값은 `국제전문학술지` 21,901, `학술회의 논문` 9,438, `국내전문학술지` 1,060, `일반학술지` 528이다. 교수 1명이 최대 1,815편을 가진다.

알려진 품질 문제(관측):
- 제목에서 하이픈 같은 문장부호가 빠져 단어가 붙어 있다. 예: `AvianInspired Claws …`. 연구자 검색 원본의 표기로 보인다.
- `year`가 정상 범위(1950–2026) 밖인 값이 650편이다: `0` 471, `20` 163, `19` 6, `2027` 7, 그 밖에 `2201`·`2106`·`1015`·`9999`. `0`은 연도 미상, `19`·`20`은 두 자리로 줄인 연도로 보인다(해석).
- 같은 교수 안에서 제목이 같은 논문(문장부호·대소문자 무시)이 2,252편 중복된다.

### 4.7 `representative_papers[]` 항목 — 대표 논문
교수별 후보 논문 중 최대 10편을 골랐다. 후보는 최근 10년(2016-10-01 이후)에 게재되고, 연구자 검색이나 연구실 사이트의 논문 목록에 있는 논문이다. 각 논문의 점수는 교수 본인의 후보 안에서 매긴 백분위의 가중합이다: `0.5×FWCI + 0.3×최근 3년(2024–2026) 인용 + 0.2×연구실 주도(교수가 마지막·교신 저자)`. 최근 5년 논문을 4편 이상 넣고, 같은 OpenAlex 주제는 4편까지만 넣는다.

| 필드 | 타입 | 의미 | 관측 |
|---|---|---|---|
| `title` | string | 제목(OpenAlex 표기) | 2,449 |
| `publication_date` | string | 게재일 `YYYY-MM-DD` | 2,449 |
| `year` | int | 게재 연도. `publication_date`의 연도와 같다 | 2016–2026 |
| `venue` | string\|null | 학술지·학회 | 2,429 |
| `doi` | string\|null | DOI(`10.`으로 시작, URL 접두 없음) | 2,445 |
| `openalex_id` | string | OpenAlex 작품 URL | 2,449 |
| `pmid`, `arxiv_id` | string\|null | PubMed·arXiv id | 1,096 / 210 |
| `topic` | string | OpenAlex 주요 주제 | 2,449 |
| `cited_by_count`, `recent_citations` | int | 전체 인용수, 최근 3년 인용수 | 2,449 |
| `fwci` | float\|null | 분야 가중 인용 지수 | 2,404 |
| `author_position` | string\|null | `first`·`middle`·`last` | last 1,280, middle 919, first 247 |
| `is_corresponding` | bool | 교수가 교신저자인지 | — |
| `score`, `score_parts` | float, object | 선정 점수(0–1)와 구성(`fwci_pct`, `recent_pct`, `lab_led`) | — |
| `abstract`, `abstract_source` | string\|null | 초록과 출처 | 2,095편. 출처: openalex 1,850, pubmed 184, arxiv 28(+`arxiv (EECS 60 run)` 2), publisher_meta 27, crossref 4 |

같은 DOI가 여러 교수의 대표 논문에 들어간 경우가 87개 있다(공동 저자). 오류가 아니다.

### 4.8 `selection_meta`
`openalex_author_ids`(교수로 확인된 OpenAlex 저자 id 목록), `openalex_works`(그 저자들의 논문 수), `candidates`(대표 논문 후보 수), `recent_swaps`(최근 5년 조건 때문에 바꾼 편수). 교수가 있는 313건에만 있다. 이 중 35건은 대표 논문이 0편이다.

### 4.9 값 분포 (관측)
- `professor.department`(19개): 전자전기공학과 36, 생명과학과 30, 물리학과 25, 컴퓨터공학과 23, 기계공학과 22, 신소재공학과 22, 수학과 21, 화학공학과 21, 화학과 21, 인공지능대학원 18, 산업경영공학과 17, 인문사회과학부 12, 친환경소재대학원 친환경소재학과 11, 환경공학부 10, 첨단원자력공학부 7, 의공학과 6, 반도체공학과 5, 친환경소재대학원 배터리공학과 5, 첨단재료과학부 1
- `departments`에만 나오는 값: 의과학전공 34, 반도체대학원 27, 의공학과 17, 합성생물학전공 10 등(겸임·전공 소속)
- `keywords` 언어: 영어 1,043개, 한국어 75개
- `research_intro` 길이: 중앙값 약 1,800자, 최대 70,980자. 20,000자를 넘는 레코드가 6건 있다.
- 같은 한글 이름의 교수: 이승우, 김정훈, 김민성, 김영진, 이상민(각 2명)

### 4.10 무결성 규칙

| ID | 등급 | 규칙 | 관측 |
|---|---|---|---|
| L-01 | 필수 | `advisor_id`는 유일하고 4.1의 세 형식 중 하나다 | 위반 0 |
| L-02 | 필수 | 16진수 `advisor_id`는 `professor.researcher_id`와 같다 | 위반 0 |
| L-03 | 필수 | `advisor_id`가 `lab:`이면 `professor`는 null이고, 그 밖이면 객체다 | 위반 0 |
| L-04 | 필수 | `display_name`은 유일하다 | 위반 0 |
| L-05 | 필수 | `professor.department == departments[0]` | 위반 0 |
| L-06 | 필수 | `lab_url == urls[0].url`이고, `urls`가 비면 `lab_url`은 null이다 | 위반 0 (빈 `urls` 44건) |
| L-07 | 필수 | `has_lab_site`는 `urls` 중 `status == "ok"`가 있을 때만 true다 | 위반 0 |
| L-08 | 필수 | `professor.email`은 `@postech.ac.kr`이고 교수 사이에 중복되지 않는다 | 위반 0 |
| L-09 | 필수 | `name_source`는 `lab_name`이 있을 때만 값이 있다 | 위반 0 |
| L-10 | 필수 | `lab_mates`의 모든 이름은 같은 `lab_group`을 가진 다른 레코드의 `professor.name`이다 | 6건 모두 상호 대칭 |
| L-11 | 필수 | `representative_papers`는 10편 이하이고, `year`가 `publication_date`와 맞고 2016–2026 안이다 | 위반 0 |
| L-12 | 권장 | `professor_papers[].year`가 1950–2026 안이다 | 위반 650 (4.6) |
| L-13 | 권장 | `professor_papers` 안에 같은 제목이 중복되지 않는다 | 중복 2,252 |
| L-14 | 권장 | `site_papers[].year`가 2026 이하다 | 위반 4 (`2027` 3, `2028` 1) |
| L-15 | 권장 | 값이 항상 null인 필드(`site_papers[].venue`·`doi`, `professor_papers[].doi`)는 정제본에서 지운다 | 3개 필드 |
| L-16 | 권장 | `research_intro`에서 사이트 메뉴 등 잔여 문구를 걷어낸다 | 앞 300자 안에 `본문 바로가기`·`메뉴`·`Skip to`가 있는 레코드 72건 |
| L-17 | 확인 | 교수 미확인 연구실(`lab:` 52건)을 추천 대상에 넣을지, 교수를 찾아 채울지 정한다 | 52건 모두 대표 논문 없음, 37건은 사이트 정상 |
| L-18 | 확인 | 연구 내용 근거가 전혀 없는 레코드를 다룰 방법을 정한다. 근거는 `research_intro`, `keywords`, `representative_papers`다 | `research_intro`와 대표 논문이 모두 없는 레코드 38건 |
| L-19 | 확인 | `match`가 약한 근거(`name_in_site_weak`, `site_llm_*`)인 교수–연구실 연결을 사람이 확인한다 | 18명 |
| L-20 | 확인 | 학과 이름 체계를 하나로 정한다(X-04) | — |
| L-21 | 확인 | `admission`을 "현재 모집 중"으로 표시하지 않는다. 게시일이 본문에만 있다 | 56건 |

### 4.11 정제본 `labs.jsonl`

`tools/build_labs.py`가 `final_labs.jsonl`(원본), `curation/advisors.jsonl`(사람 검증), `curation/lab_overrides.json`(검토 뒤 사람이 정한 이름·링크·OpenAlex 프로필), `curation/openalex_paper_match.json`(학교 연구자 검색 논문 목록과 OpenAlex 프로필 대조, 사례집 D-11), `curation/openalex_profile_check.json`(OpenAlex 프로필 소속 검사, D-10)을 합쳐 만든다. 계획과 형식 규칙은 [정제본 계획](../docs/plans/2026-10-25-lab-data-normalization.md), 규칙 코드는 `tools/normalize.py`다. 입력이 바뀌면 다시 만들고, `python3 tools/build_labs.py --check`로 최신인지 확인한다.

- **1줄 = 교수·연구실 기록 1건, 365건 모두.** 추천 제외 기록도 이유와 함께 남긴다. 추천에 쓸 기록은 `recommendable == true`(307건)로 거른다.
- 모든 레코드가 같은 키를 같은 순서로 가진다(G-02). 결측은 문자열·객체 `null`, 목록 `[]`, 참거짓 `false`다(G-03). 본문 줄바꿈은 `\n`이다(G-04).
- 형식을 바꾼 값은 원래 값을 함께 둔다: 연구실 이름은 `lab.raw`, 연구 분야는 항목마다 `raw`(바뀐 경우만). 지운 것은 URL의 세션·로그인 매개변수, 줄 끝 공백, 3줄 이상 빈 줄, 폭 없는 문자뿐이다.
- 교수 이메일은 넣지 않는다(G-06). 필요하면 원본에서 `id`로 찾는다.
- 사람이 정한 연구실 이름과 바로잡은 링크·OpenAlex 프로필은 `curation/lab_overrides.json`(`{id: {name_ko, name_en, acronym, alias, url, source, why, openalex_author_ids, openalex_why, openalex_source, decided}}`)에 두면 검토 기록보다 먼저 쓴다. OpenAlex 프로필은 `tools/match_openalex_papers.py --apply`가 근거 숫자와 함께 적는다(2026-10-26: 25곳). `source`는 이름을 확인한 사이트, `why`는 이유다(사례집 A-15·A-16). 규칙이 바꾼 이름과 아직 사람이 정하지 않은 이름 목록은 `curation/normalize_report.json`에 있다(2026-10-25 기준 0곳).

| 필드 | 타입 | 의미 |
|---|---|---|
| `id` | string | `final_labs.advisor_id`와 같다 |
| `kind` | string | `professor`(교수 기록) · `lab_only`(교수 미확인 연구실 기록, 원본 `lab:` id) |
| `status` | string | 사람 검증 결과 `verified` · `excluded` |
| `recommendable` | bool | 추천에 써도 되는지(`verified`이고 퇴임·이직이 아님) |
| `exclusion` | object\|null | 추천 제외 이유 `{kind, of}`. `kind`: `duplicate`(같은 연구실, `of` = 합친 교수 기록 `id`) · `left`(퇴임·이직·명예교수) · `not_a_lab`(교수 연구실이 아님) · `professor_not_found`(지도교수를 찾지 못함) · `other`(이유는 `note`) |
| `professor` | object | `name_ko`, `name_en`, `position`, `departments`(학교 공식 명칭, 첫 값이 대표 학과), `researcher_id`, `in_researcher_db`. `lab_only` 기록은 검토자가 찾은 지도교수 |
| `lab.name` | string\|null | 표시 이름. 한글 이름(없으면 영문 풀네임) 뒤에 `(약자)` 또는 `(별칭)`. 이름이 없으면 `○○○ 교수 연구실`(사례집 A-07) |
| `lab.name_ko`, `lab.name_en` | string\|null | 한글 이름, 영문 풀네임(약자를 뺀 이름). 약자만 있는 연구실은 `name_en`이 null이다(지어내지 않는다) |
| `lab.acronym`, `lab.alias` | string\|null | 약자(`ACOL`, `PL Lab`), 약자가 아닌 다른 이름(`Seo Research Group`) |
| `lab.raw` | object | 검증 결과의 원래 이름과 링크 `{name, name_ko, name_en, url}` |
| `lab.url`, `lab.link_kind`, `lab.url_status`, `lab.extra_links` | | 확정한 링크와 종류(`lab_site`·`personal_page`), 링크 상태(`confirmed`·`corrected`·`none`·`unreviewed`), 추가 링크 |
| `lab.group`, `lab.mates`, `lab.centers` | | 원본의 공동 연구실 묶음, 같은 연구실의 다른 교수, 소속 연구센터 |
| `intro` | object | `text`(사람이 옮긴 연구소개 원문), `chars`, `source_url`, `source_kind`, `is_image`, `image_page_urls`, `noise`(본문에 남은 사이트 잔여물 종류, 예 `script_code`. 지우지 않고 표시만 한다) |
| `research_areas` | array | `{name, name_en, name_ko, kind, raw}`. `kind`: `area` · `heading`(끝이 `:`인 소제목) · `sentence`(분야 이름이 아니라 설명 문장). 두 언어로 쓴 이름은 `name_en`·`name_ko`로도 나눈다 |
| `research_areas_none` | bool | 글에 분야 제목이 없음 |
| `employment` | string | `active` · `left` · `unknown` |
| `openalex` | object | `status`(`confirmed` · `not_found` · `corrected`: 검토 뒤 사람이 `lab_overrides.json`으로 고침), `author_ids`(쓸 프로필), `raw_author_ids`(검토 기록의 원래 값), `profiles`(프로필마다 `works_count`, `postech_works`, `flag`(`strong`·`weak`·null), `reasons`(사례집 D-10), `listed_hits`(학교 연구자 검색 논문 목록 중 이 프로필에 있는 편수), `verdict`(`confirmed` · `weak` · `no_match` · `unverifiable` · `empty`, 사례집 D-11)) |
| `scholar_url`, `note` | string\|null | 구글 스칼라 링크, 검토 메모 |
| `review` | object | `by`, `at`, `seconds_spent`, `queue_generated_at`, `intro_blocks`, `duplicate`, `pi_source_url`, `pi_not_found` |


### 4.12 연구실 대표 논문 `papers.jsonl`

`tools/select_papers.py`가 `labs.jsonl`의 추천 가능 307곳마다, 확정한 OpenAlex 프로필의 논문 중 본인 논문을 골라 최대 10편을 뽑는다. 원본의 `representative_papers`(4.7)를 대신한다. 규칙과 평가는 [논문 선정 v2](../docs/plans/2026-10-26-paper-selection-v2.md)에 있다. `python3 tools/select_papers.py --check`로 최신인지(캐시로), `--compare`로 이전 선정과의 비교를 본다.

- 1줄 = 연구실 1곳(`id`는 `labs.jsonl`과 같다), 307줄. 논문이 있는 곳 300곳, 논문 2,768편. 0편 7곳은 OpenAlex 프로필이 없는 6곳과 김성웅(사례집 D-15)이다.
- 본인 논문: 학교 연구자 검색 목록에 있거나(`in_list`), POSTECH 소속으로 썼거나(`postech_affiliation`), 목록 대조로 확인됐거나 확인할 수 없는 깨끗한 프로필의 논문(D-10·D-11·D-15).

| 필드 | 타입 | 의미 |
|---|---|---|
| `id`, `professor`, `author_ids` | | 연구실 기록 id, 교수 이름, 쓴 OpenAlex 프로필 |
| `basis` | string | `lab_led`(연구실 주도 논문으로 고름) · `all_authors`(연구실 주도 논문이 5편 미만이라 모든 논문으로, 저자 알파벳순 분야 등) · `no_openalex` |
| `core_topics`, `areas_matched` | array | 핵심 분야로 본 OpenAlex 주제, 선정 논문에서 찾은 연구 분야 이름(D-12) |
| `counts` | object | `works_since_2018`, `own`, `own_by`(본인 논문 판정 근거별 수), `window`, `lab_led` |
| `papers[]` | array | 고른 논문(최신순). 아래 필드 |
| `openalex_id`, `doi`, `title`, `year`, `date`, `venue`, `type`, `source_type`, `publisher` | | 서지 정보. `type`: `article` · `conference-paper` · `preprint` · `review` · `book-chapter` |
| `topic`, `subfield`, `fwci`, `cited_by_count`, `authors_count` | | OpenAlex 주요 주제·분야, 분야 가중 인용 지수, 인용 수, 저자 수 |
| `author_position`, `is_corresponding`, `lab_led` | | 교수의 저자 위치, 교신저자 여부, 연구실 주도(마지막 저자 또는 교신저자) |
| `in_list`, `postech_affiliation`, `cited_on_site` | bool | 학교 목록에 있음, POSTECH 소속으로 씀, 연구소개에 제목이 나옴(D-14) |
| `abstract`, `abstract_source` | string\|null | 초록과 출처: `openalex` · `openalex_other_version` · `crossref` · `pubmed` · `semantic_scholar`. 2,768편 중 198편은 null(D-03) |
| `versions` | array | 같은 논문의 다른 OpenAlex 기록(프리프린트·다른 판·저장소 사본, D-13) |
| `reasons` | array | 선정 이유: `cited` · `core` · `area` · `recent` · `emerging` · `review` · `fill` |
---

## 5. `research_centers.jsonl` — 연구센터

연구센터·연구단·연구소처럼 지도교수 레코드가 아닌 연구 조직이다. 이름에 `센터`·`연구단`·`연구소`·`Center`·`Institute` 등이 들어간 연구실 사이트를 따로 모았다.

| 필드 | 타입 | 필수 | 의미 | 관측 |
|---|---|---|---|---|
| `lab_id` | string | 예 | 정규화 URL(키, 유일) | 29 |
| `name` | string | 예 | 센터 이름(유일) | 29 |
| `lab_url` | string | 예 | URL | 29 |
| `departments` | array\<string\> | 예 | 관련 학과 | 29 |
| `status` | string | 예 | 크롤링 결과(`ok`·`needs_review`) | ok 21, needs_review 8 |
| `professors` | array\<string\|null\> | 예 | 소속 교수 이름 | 비어 있음 18, **null 원소 1** |
| `research_intro` | string\|null | 아니오 | 소개 본문 | 19 |
| `keywords` | array\<string\>\|null | 아니오 | 키워드 | 20 |

| ID | 등급 | 규칙 | 관측 |
|---|---|---|---|
| R-01 | 필수 | `lab_id`와 `name`은 유일하다 | 위반 0 |
| R-02 | 권장 | `professors`에 null 원소가 없다 | 위반 1 |
| R-03 | 확인 | 센터를 추천 결과에 보여줄지, 교수 레코드의 소속 정보로만 쓸지 정한다 | — |

---

## 6. 파일 간 관계

공식 외래 키는 없다. **이름 문자열로만** 연결되는 관계가 많으므로, 동명이인과 표기 차이를 검증해야 한다.

```
final_courses.professor (이름) ──?──▶ final_labs.professor.name     ← 이름만 일치, 키 없음
final_courses._dept     (학과) ──?──▶ final_labs.departments[]      ← 학과명 체계가 다름
final_labs.centers[]    (이름) ──────▶ research_centers.name
research_centers.professors[] (이름) ─▶ final_labs.professor.name
final_labs.lab_mates[]  (이름) ──────▶ final_labs.professor.name (같은 lab_group)
```

| ID | 등급 | 규칙 | 관측 |
|---|---|---|---|
| X-01 | 필수 | `final_labs.centers[]`의 모든 값이 `research_centers.name`에 있다 | 13/13 |
| X-02 | 필수 | `research_centers.professors[]`의 null이 아닌 이름이 `final_labs.professor.name`에 있다 | 13/13 |
| X-03 | 확인 | 과목 담당교수와 지도교수를 연결할 방법을 정한다. 이름만으로 연결하면 동명이인 5쌍이 섞인다 | **결정(2026-10-26): 이름과 학과가 맞을 때 잇는다.** 학과는 대응표(X-04)로 맞추고 교수의 겸임 학과도 본다. 교수 소속이 따로 없는 과정(융합대학원 등)이나 다른 학과 과목을 가르치는 경우는 같은 이름의 교수가 한 명뿐일 때만 이름으로 잇는다. 연결마다 근거(`basis`)를 남긴다: 담당교수 이름 1,155개 중 이름+학과 785, 이름만(유일) 194, 동명이인이라 못 정함 4, 연구실 데이터에 없음(강사 등) 172 |
| X-04 | 확인 | 학과명 대응표를 만든다. 과목에만 있는 이름: IT융합공학과, 융합대학원, 배터리공학과, 친환경소재학과, 시스템생명공학부, 교육혁신센터, 무은재학부, 포스텍-삼성전자 반도체 교육프로그램, 스포츠 AIX 융복합 대학원 프로그램. 연구실에만 있는 이름: 친환경소재대학원 친환경소재학과, 친환경소재대학원 배터리공학과, 의과학전공, 합성생물학전공 | **결정(2026-10-26): 대응표 `curation/departments.json`을 만들었다.** IT융합공학과 → 의공학과(2026년 이름 변경, 학수번호 앞 글자 CITE가 같음), 친환경소재학과·배터리공학과 → 친환경소재대학원의 두 학과. 융합대학원·시스템생명공학부·교육혁신센터·무은재학부·교육 프로그램은 교수 소속이 따로 없이 여러 학과 교수가 겸임으로 가르치는 과정(`program`), 의과학전공·합성생물학전공은 교수의 겸임 소속(`major`)으로 둔다 |
| X-05 | 확인 | 과목–연구실 연결(어떤 과목이 어떤 연구에 도움이 되는지)은 이 데이터에 없다. 추천에 필요하면 별도로 만든다 | — |

### 6.1 레거시 데이터와의 대응
- 레거시 `labs.jsonl`의 교수 65명은 모두 `final_labs.jsonl`에 이름으로 있다. id 체계는 다르다(`record_id` ↔ `advisor_id`).
- 레거시 `courses.jsonl`의 학수번호 419개 중 337개가 `final_courses.jsonl`에 있다. 나머지 82개는 2025-1 ~ 2026-2에 열리지 않았거나 학수번호가 바뀐 과목으로 보인다(해석).
- 레거시 프로필·개념 어휘·골드셋·커뮤니티 시드는 레거시 id를 참조한다. 새 데이터로 옮길 때 다시 만들거나 id를 대응시켜야 한다.

---

## 7. 사용 원칙

- 수집 자료는 공개 웹페이지와 학내 시스템의 **수집 시점 사본**이다. 현재 개설 여부, 현재 모집 여부, 연구실 분위기·지도 방식은 이 데이터로 단정하지 않는다.
- `keywords`의 일부와 `lab_name`의 일부(`name_source=site_llm`)는 LLM이 추출했다. 사실 근거로 보여줄 때는 원문(`research_intro`, 논문 제목·초록)을 함께 보여준다.
- 대표 논문의 선정 점수는 연구실 간 비교용이 아니다. 교수 본인의 논문 안에서 매긴 백분위다.
- 강의계획서의 조교 연락처와 교수 이메일은 G-06 결정 전까지 화면에 노출하지 않는다.

## 8. 검증 진행

검증 결과는 규칙 ID별로 기록한다. 기록 위치와 형식(검증 스크립트·보고서)은 검증을 시작할 때 이 절에 추가한다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | `필수` 규칙을 자동 검사로 확인 | 대기 |
| 2 | `권장` 규칙 위반의 정제 방안 결정 | 대기 |
| 3 | `확인` 항목 결정(사람 판단) | 대기 |
| 4 | 정제본 생성과 앱 이전 | 연구실 정제본(`labs.jsonl`, 4.11), 과목 정제본(`courses.jsonl`, 3.6), 대표 논문(`papers.jsonl`, 4.12) 완료. 앱 이전은 추천 엔진 설계와 함께 |

## 9. 변경 기록

| 날짜 | 변경 |
|---|---|
| 2026-10-13 | `feat/vectorRAG`(`d358143`)에서 `final_courses.jsonl`, `final_labs.jsonl`, `research_centers.jsonl`을 가져왔다. 기존 4개 학과 MVP 데이터 8개는 `legacy/mvp-4dept/`로 옮겼다. 이 문서를 새 데이터 기준으로 다시 썼다 |
| 2026-10-25 | 연구실 정제본 `labs.jsonl`을 추가했다(`tools/build_labs.py`, 4.11). 원본 세 파일은 그대로다. 학과 이름 `인문사회과학부`는 정제본과 검증 대기열에서 공식 명칭 `인문사회학부`로 쓴다(사례집 A-14) |
| 2026-10-25 | **원본 수정(G-05 예외, 사용자 허용):** `final_labs.jsonl`의 `professor.department`·`departments[]` 값 `"인문사회과학부"` 24곳(12건)과 `final_courses.jsonl`의 `_dept` 값 123곳을 POSTECH 공식 명칭 `"인문사회학부"`로 바꿨다. 원본에 잘못 들어간 값이 확실해서 바로잡는 목적이다. 값 전체가 정확히 `인문사회과학부`인 칸만 바꿨고, 강의계획서 본문 속 표기(1곳)와 과목 구분 `인문사회과학선택`, 수집 기록(`curation/crawl/`)은 그대로다. 새 해시는 1.1절. 사람이 정한 연구실 이름 14곳과 링크 2곳은 `curation/lab_overrides.json`에 두고 정제본에 반영했다(4.11) |
| 2026-10-26 | 정제본의 OpenAlex 프로필을 학교 연구자 검색 논문 목록(`professor_papers`)과 제목으로 대조해 고쳤다(`tools/match_openalex_papers.py`, 사례집 D-11). 25곳: 프로필 24개를 빼고 11개를 더해 338개 중 290개가 목록으로 본인 확인됐다. 정제본 `openalex`에 `raw_author_ids`, 프로필마다 `listed_hits`·`verdict`를 더했고, `status`에 `corrected`가 생겼다. 원본·검토 기록은 그대로다 |
| 2026-10-26 | 과목 정제본 `courses.jsonl`과 학과 대응표 `curation/departments.json`을 추가했다(`tools/build_courses.py`, 3.6). 사용자 결정: 학점 0·연구과목은 추천에서 뺌(C-09), 담당교수가 없으면 "담당교수 미정"(C-11), 연락처·접속 정보 가림(C-13), 담당교수–지도교수는 이름+학과로 잇고 겸임 과정은 유일한 이름으로만(X-03), IT융합공학과 → 의공학과 등 대응표(X-04). 원본은 그대로다 |
| 2026-10-26 | 연구실 대표 논문 `papers.jsonl`을 추가했다(`tools/select_papers.py`, 4.12). 원본 `representative_papers`와 비교해 연구실 주도 비율 0.72 → 0.91, 2024년 이후 비율 0.31 → 0.47, 초록 비율 0.86 → 0.93, 논문이 있는 연구실 276 → 300곳 |
