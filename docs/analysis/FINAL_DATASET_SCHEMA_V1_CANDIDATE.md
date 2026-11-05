# 최종 JSONL 정규 스키마 v1 후보

작성일 2026-10-14. 입력은 저장소 루트의 `final_courses.jsonl`과 `final_labs.jsonl`이다. 이 문서는 **구조 계약 후보**이며 두 Luna 심사위원의 성능 판정 전에는 추천 정책의 확정 결론이 아니다. 원본 JSONL은 수정하지 않고 출처 보존 정규화와 후보 관계를 별도 저장한다.

## 범위와 식별자

| 레코드 | 기본 키 | 해석 |
|---|---|---|
| `course` | `course:<canonical_code>` | 현재 파일에서 과목 코드는 1,316개 모두 고유하다. 제목·내용이 같은 코드는 자동 교차 개설로 병합하지 않는다. |
| `course_offering` | 파일 해시·원본 행 기반 `offering_id` | 학기·교수·학과·학점은 개설 속성이다. |
| `source_evidence` | `evidence_id` | 과목 설명·학습목표·진도, 연구실 소개, 수록 논문 제목·초록의 원문 조각이다. 현재 적격 과목의 목표는 설명과 동일하므로 독립 근거로 중복 계산하지 않는다. |
| `advisor` | 원본 `advisor_id` | 교수 개인이다. |
| `lab` | 임시 `lab_id` | 추천 대상 연구실 후보이며 현재는 교수별 임시 ID다. 동일 사이트나 `lab_group` 문자열만으로 합치지 않는다. |
| `lab_membership` | `lab_id` + `advisor_id` + 출처 | 교수와 연구실의 수록 관계 후보이다. |
| `paper` | DOI/OpenAlex ID 우선, 없으면 출처별 임시 ID | 제목 유사성은 중복 후보일 뿐 동일 논문 확정이 아니다. |
| `paper_lab_evidence` | 출처 행·목록·목록 내 위치로 정한 `claim_id` | 논문이 원본 목록에 수록되었다는 주장이다. 연구실 대표성 검증과 구별한다. |
| `concept` | 통제 어휘 ID | `domain`, `problem`, `method`, `tool`, `material`, `knowledge`를 구분한다. |
| `assertion` | 원문 span 및 양 끝 노드로 결정되는 ID | 자동 추출 관계는 검토 전 후보 주장이다. |

모든 원본 유래 레코드는 `source_file`, `source_sha256`, 1부터 시작하는 `source_row`, 해당하는 경우 `source_field`와 `[start,end)` 문자 범위를 보존한다. `schema_version`, `extractor_version`, `review_status`, `assertion_origin`을 함께 기록한다. `null`은 미확인, 빈 문자열은 정제 후 미확인, 명시적 ‘없음’은 별도 상태다. 결과가 0점인 것과 근거가 부족해 보류한 것은 다른 상태다.

### 기계 검증용 계약 초안

| 레코드 | 필수·비어 있지 않은 필드와 형식 | 선택 필드와 관계 수 |
|---|---|---|
| `course` | `course_id`, `canonical_code`, `title`: 문자열; `source`: 출처 객체 | `code_aliases`: 문자열 배열(기본 `[]`); `crosslist_group_id`: 문자열 또는 `null`. 과목 하나에 개설 1개 이상. |
| `course_offering` | `offering_id`, `course_id`: 문자열; `source`: 출처 객체 | `semester`, `professor_name`, `department`, `credit_original`, `category`: 문자열 또는 `null`. 개설 하나는 과목 하나를 가리킴. |
| `advisor` | `advisor_id`, `name`: 문자열; `source`: 출처 객체 | `department`, `researcher_id`: 문자열 또는 `null`. |
| `lab` | `lab_id`, `name`: 문자열; `source`: 출처 객체 | `canonical_url`, `lab_group_candidate`: 문자열 또는 `null`; `departments`: 문자열 배열. 현재 임시 연구실은 교수 하나에 대응하지만 최종 연구실의 교수 수는 1개 이상일 수 있음. |
| `lab_membership` | `lab_id`, `advisor_id`, `role`, `review_status`: 문자열; `source`: 출처 객체 | 연구실·교수 쌍에 서로 다른 원본 주장이 여러 개 있을 수 있음. |
| `paper` | `paper_id`, `title`, `identity_basis`: 문자열; `source`: 출처 객체 | `year`: 정수 또는 `null`; `doi`, `openalex_id`, `abstract`, `venue`: 문자열 또는 `null`. |
| `paper_lab_evidence` | `claim_id`, `paper_id`, `lab_id`, `advisor_id`, `source_list`, `evidence_level`, `verification_status`: 문자열; `source_index`: 비음수 정수; `source`: 출처 객체 | `source_list`는 단일 문자열이며 `site_papers`, `professor_papers`, `representative_papers` 중 하나. 논문·연구실 쌍에 출처 목록·위치별 주장이 여러 개 있을 수 있음. |
| `source_evidence` | `evidence_id`, `owner_kind`, `owner_id`, `text`, `field`, `review_status`: 문자열; `source`: 출처 객체; `span`: 길이 2의 비음수 정수 배열 | `owner_kind`는 `offering`, `lab`, `paper_listing` 중 하나이고 `owner_id`는 각각 `offering_id`, `lab_id`, `paper_lab_evidence.claim_id`를 참조. `span`은 해당 최종 JSONL 원본 필드 문자 오프셋이며 `end > start`. |
| `concept` | `concept_id`, `canonical_label`, `concept_type`: 문자열 | `concept_type`은 `domain`, `problem`, `method`, `tool`, `material`, `knowledge` 중 하나. `aliases`: 비어 있지 않은 문자열 배열; 어휘 버전을 별도로 고정. |
| `assertion` | `assertion_id`, `subject_id`, `predicate`, `object_concept_id`, `evidence_id`, `extractor_version`, `review_status`, `assertion_origin`: 문자열; `span`: 길이 2의 비음수 정수 배열 | `predicate`는 `uses`, `develops`, `studies`, `teaches`, `prerequisite_code_mention`, `prerequisite_knowledge_mention` 중 하나. 한 근거에 서로 다른 관계가 공존할 수 있음. |

이 표의 `concept`·`assertion` 행은 staging v2 이후 구현할 계약이다. `course_id`는 정확히 `course:<canonical_code>`이고 `canonical_code`는 양 끝 공백을 제거한 대문자 코드다. 각 `course_offering.course_id`는 존재하는 과목을 가리켜야 하며 이 최종 JSONL 스냅샷에서는 모든 과목의 개설 수가 1개 이상이어야 한다. `concept_id`는 고정 어휘 버전의 명시적 ID를 유지한다. `assertion_id`는 `extractor_version`, `subject_id`, `predicate`, `object_concept_id`, `evidence_id`, `span`을 길이 구분된 정규 직렬화로 연결해 SHA-256 해시로 만든다. 출처 객체의 필수 키는 `source_file`(허용값: 두 최종 JSONL 파일명), 64자리 소문자 SHA-256 `source_sha256`, 양의 정수 `source_row`, 비어 있지 않은 `source_field`, `schema_version`이다. 외래 키는 같은 스냅샷 안에서 존재해야 한다.

식별자의 안정성 범위를 구별한다. `course:<canonical_code>`는 코드가 유지되는 소스 버전 사이에서 안정적인 논리 ID다. `advisor:<원본 advisor_id>`와 `lab:<원본 advisor_id>`는 공급자가 교수 ID를 유지하는 동안만 안정적이며, `lab_id`는 교수 수준 임시 식별자이므로 실제 연구실의 장기 ID로 쓰지 않는다. `offering_id`, 출처별 임시 `paper_id`, `evidence_id`, 자동 추출 `assertion_id`는 파일 해시나 원문 위치가 바뀌면 새로 발급되는 **스냅샷 ID**다. 버전 사이 동일 개체 연결은 별도 검토 매핑으로 관리한다.

선택 문자열 값은 저장 시 공백을 제거하고 빈 값이면 `null`로 정규화한다. 원본이 비었는지, 필드가 누락됐는지, 명시적으로 ‘없음’이라고 했는지는 `value_state`의 `source_blank`, `source_missing`, `explicit_none`, `present`, `not_checked` 중 하나로 별도 보존한다. 현재 staging v2는 이 상태를 모두 출력하지 않으므로 이 부분은 **구현 전 계약**이다. 추천 판단 상태는 `scored`, `insufficient_evidence`, `not_applicable`로 나누고 `scored`일 때만 숫자 점수를 허용한다.

## 추천에 쓰는 관계

`paper_lab_evidence.claim_id`와 논문별 `source_evidence`의 소유 연결은 staging v2에 구현했다. 논문 제목·초록의 원문 필드 경로와 span도 저장한다. 그러나 자동 추출 assertion의 근거 외래 키와 의미 관계 검증은 아직 구현되지 않았다. 논문에서 나온 assertion은 `paper_lab_evidence.claim_id`로 특정 목록 수록 occurrence를, `source_evidence.evidence_id`로 그 occurrence의 제목 또는 초록 원문을 모두 참조해야 한다. `claim_id`는 파일 해시·행·목록명·목록 내 0기반 위치를 길이 구분해 직렬화한 해시로 만든 스냅샷 ID다. 논문 원문 필드 경로는 `representative_papers[0].abstract`처럼 0기반 인덱스와 `title`/`abstract`를 포함하고, 문자 span은 그 중첩 문자열 내부의 `[start,end)`를 뜻한다. `paper_lab_evidence.source_list`는 배열이 아닌 단일 목록명 문자열이다.

`evidence_id`도 파일 해시·1기반 행·정규화된 중첩 필드 경로·문자 span의 시작/끝을 길이 구분해 직렬화한 뒤 SHA-256으로 결정한다. 같은 원문 범위를 서로 다른 assertion이 재사용할 수 있으며, 그 경우 `evidence_id`를 새로 만들지 않는다. `claim_id`와 `evidence_id`의 직렬화 형식과 해시 전체 길이는 구현 시 스키마 버전에 고정하고 충돌 검사를 수행한다.

| 후보 변 | 허용되는 근거 | 규칙에서의 용도 |
|---|---|---|
| `lab/paper --uses--> method/tool` | 소개의 연구실 자기 행위 또는 논문 초록의 해당 연구 행위와 정확한 개념 span | 같은 개념을 과목이 가르칠 때 `supports_method/tool` 후보 |
| `lab/paper --develops--> method` | 제안·개발 행위와 정확한 방법 span | 같은 개념을 과목이 가르칠 때 낮은 가중치의 `supports_method_development` 후보 |
| `lab/paper --studies--> domain/problem/material` | 연구 주제·재료의 원문 span | 탐색·필터용. 같은 주제라는 이유만으로 준비 과목으로 올리지 않음 |
| `course_offering --teaches--> method/tool` | 제목, 설명/학습문장, 진도계획 구간의 원문 span | 위 직접 연결의 과목측 근거. 단일 진도 텍스트 구간은 반복 구간보다 약하게 취급 |
| `course --prerequisite_*_mention--> code/knowledge` | 선수사항 필드의 코드·지식 문자열과 문맥 | 검토 큐 전용. 필수 선수 관계로 자동 승격하지 않음 |

연결 결과는 연구실 근거 assertion ID, 과목 근거 assertion ID, 개념 ID, 관계 유형, 점수와 보류 사유를 반환한다. `uses`와 `develops`가 한 문장에 함께 있을 수 있으므로 출처 문맥을 검토하기 전 단일 동작 사실로 단정하지 않는다. `course teaches`의 `coverage`는 `title`, `learning_statement`, `single_plan_segment`, `repeated_plan_segments`이며 구간 수는 수업 회차 수가 아니다. 논문 수·반복 개설 수가 많다는 이유로 점수를 무한 누적하지 않는다.

보류 평가 후 진단에서 같은 단어가 다른 뜻으로 쓰이는 문제가 드러났다. 예를 들어 `pair:000e492ab20d978a`의 논문 작성 *logic*은 회로의 논리와 다르고, `pair:013ddd2a0645d5cc`의 테라헤르츠파 *manipulation*은 로봇 조작과 다르다. 이 사례는 두 심사위원이 모두 0점으로 판정한 쌍을 결과 후 살펴본 **오류 진단**이며 현재 규칙을 재조정해 같은 보류 집합에서 성능을 주장하는 근거가 아니다. 다음 버전에는 `concept_sense_id`, 원문 주변 문맥, 대상 객체와 도메인 제약, 모호성 보류 사유를 assertion에 추가하고, 의미가 다른 alias를 같은 개념 ID로 연결하지 않도록 개발 집합에서 별도 검증해야 한다.

## 정보량 상태

현재 작동상 풍부한 행 후보는 설명·진도 길이를 충족한 과목 941/1,316행, 소개 길이와 첫 5개 대표 논문 중 제목·초록 조건을 충족한 연구실 203/365행이다. 연구실 203행은 공유 근거 156개 구성요소다. 이 기준은 의미상 완전성 보증이 아니다. 실제 자료에서는 소개에 메뉴·모집 공고가 섞이고, 논문 초록과 소개의 정보량이 다르므로 `intro_research_quality`, `paper_abstract_available`, `course_plan_quality` 등 근거 종류별 품질 상태를 기록해야 한다. 적격하지 않은 행을 서비스에서 0점으로 취급하지 않고 `insufficient_evidence`로 둔다.

첫 5개 대표 논문 중 제목과 100자 이상 초록을 갖춘 건수는 적격 203행에서 1건 9행, 2건 17행, 3건 25행, 4건 33행, 5건 119행이다. 따라서 같은 적격 집합 안에서도 논문 근거량 차이가 크다. 최종 추천 결과에는 사용한 실제 논문 근거의 개수와 원문 범위를 표시하고, 단순 적격 여부를 신뢰도 점수로 쓰지 않는다.

샘플 검토에서 과목 `EECE482`, `PHYS413`, `PMSE601` 등은 구체적 설명과 진도를 갖췄다. 연구실 소개 320행은 주로 모집 안내지만 대표 논문 초록에는 광촉매 연구 내용이 있다. 따라서 행 수준 텍스트 길이와 **관계별 근거 충족**을 분리해야 한다. 현재 스키마는 이를 담을 필드를 제안하며 근거 충족의 정확도는 관계 실험에서 제한적으로만 심사됐다.

## 평가 경계

v15 관계 엔진은 적격 과목 941개를 모두 추천 후보로 사용한다. 보류 집합 137공유 근거 구성요소 중 112개를 고정 시드로 뽑아 두 Luna가 910개 고유 상위 5개 쌍을 블라인드 평가한다. 두 심사위원의 910쌍 판정과 제한 분석은 완료됐다. B1 단독 추천은 낮은 반환율·고정 슬롯 효용 때문에 채택 근거를 얻지 못했다. 연결 정확도와 실제 서비스 채택은 별도 검증이 필요하다. 자세한 제한과 해시는 `experiments/final_graph/PREREG_RICH_FRAME.md` 및 `results/frozen_relation_design_v15.json`에 있다.

## staging v2 구현 상태

`normalize.py`는 원본을 변경하지 않고 `paper_lab_evidence.claim_id`·`source_index`, 논문 목록 occurrence를 소유자로 하는 제목·초록 근거, `owner_kind`, 정확한 중첩 필드 경로와 원문 문자 span을 출력한다. `results/staging_v2_validation.json`은 37,417개 목록 주장 ID와 48,645개 근거 ID의 고유성, 모든 근거 소유 외래 키, 모든 원문 span의 정확한 일치를 검사한 결과다. 논문 동일성, 연구실 병합, 의미 관계, `value_state`는 여전히 검토 대상이다. 이 상태는 스키마 전체 계약의 완성이 아니다.
