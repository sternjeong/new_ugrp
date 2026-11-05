# 최종 JSONL의 근거 중심 스키마와 추천 규칙 결정안

작성일 2026-10-15. 입력은 `final_courses.jsonl` 1,316행과 `final_labs.jsonl` 365행이다. 이 문서는 두 Luna 결과 심사와 후속 실험을 반영해 검토할 **제품 계약 결정안**이다. 원본 JSONL은 원자료로 유지하고, 아래 레코드를 별도 버전의 파생 자료로 만든다. `FINAL_DATASET_SCHEMA_V1_CANDIDATE.md`의 식별자·외래 키·원문 span 명세가 상세 계약이다.

## 1. 소스와 엔터티

| 레코드 | 결정 | 이유 |
|---|---|---|
| `course`, `course_offering` | 과목 코드와 개설 정보를 분리; 제목이 비슷한 서로 다른 코드는 자동 병합하지 않음 | 다른 코드의 동일 내용·교차 개설은 확인 전 별개 |
| `advisor`, `lab`, `lab_membership` | 교수와 연구실을 분리; 현재 `lab:<advisor_id>`는 임시 ID | 동일 URL·`lab_group`만으로 교수 행을 합치면 원문 수록 관계를 잃음 |
| `paper`, `paper_lab_evidence` | DOI/OpenAlex가 있을 때만 논문 동일성 연결; 목록별 수록 주장을 `claim_id`로 유지 | 논문 수록은 현재 연구실 대표성의 확정이 아님 |
| `source_evidence` | 출처 파일 SHA, 행, 중첩 필드 경로, 정확한 문자 span, 소유 claim ID와 원문 보존 | 규칙의 각 연결을 사용자가 원문까지 되짚을 수 있음 |
| `concept`, `concept_sense` | 도메인·문제·방법·도구·재료·지식을 구분하고 다의어 뜻 ID를 별도로 둠 | `logic`, `manipulation`처럼 같은 단어의 다른 뜻이 거짓 연결을 만듦 |
| `assertion` | 주어·관계·대상 뜻 ID·원문 근거·추출기 버전·검토 상태를 기록 | 문자열 명중과 실제 `uses/develops/studies/teaches`를 혼동하지 않음 |
| `recommendation_evidence` | 연구실 주장·과목 주장·개념 뜻·점수 구성·판정 상태를 한 연결별로 저장 | 결과가 왜 나왔는지와 왜 보류됐는지를 분리 |
| `query_intent` | 사용자 원문, 좋아함·싫어함 구절과 span, 모호성·보류 상태, 해석기 버전 | 싫다는 주제를 긍정 검색어로 섞지 않고 해석 실패를 드러냄 |

`query_intent`는 최종 두 JSONL의 필드가 아니라 서비스 질의에서 생성하는 파생 레코드다.

`source_evidence.owner_kind`는 `offering`, `lab`, `paper_listing`이며 논문 제목·초록의 `owner_id`는 해당 `paper_lab_evidence.claim_id`다. `paper_listing` 원문 span은 `representative_papers[0].abstract` 같은 원본 중첩 문자열 내부의 `[start,end)`다. 모든 출처 유래 ID 중 claim·evidence는 스냅샷 원문 위치를 길이 구분 직렬화해 SHA-256 전체 해시로 만든다. 공급자의 과목 코드·교수 ID가 바뀌면 버전 간 연결은 별도 검토 매핑을 거친다.

### 관계와 추천 레코드의 필수 계약

| 레코드 | 필수 필드 | 불변 조건 |
|---|---|---|
| `concept_sense` | `concept_sense_id`, `concept_id`, `concept_type`, `definition`, `vocabulary_version`, `review_status` | 뜻 ID는 버전 안에서 불변이다. 다른 버전의 동의어·뜻 병합·분할은 검토된 `sense_mapping`으로만 연결하며 다른 뜻을 자동 동일시하지 않음 |
| `sense_mapping` | `mapping_id`, `from_sense_id`, `to_sense_id`, `mapping_kind`, `review_status`, `mapping_version` | `mapping_kind`는 `same_meaning`, `broader`, `narrower`, `split`, `merged` 중 하나; `review_status`는 `unreviewed`, `accepted`, `rejected`, `ambiguous` 중 하나. 양 끝 뜻 ID와 버전을 외래 키로 확인하고 `(from_sense_id,to_sense_id,mapping_kind,mapping_version)`은 유일. 한 출발 뜻에 여러 도착 뜻을 허용하되 자동 동치 연결은 `accepted`된 `same_meaning`에만 허용 |
| `assertion` | `assertion_id`, `subject_kind`, `subject_id`, `predicate`, `object_concept_sense_id`, `evidence_id`, `extractor_version`, `review_status`, `assertion_origin` | `evidence_id`가 실제 원문을 가리킴. `subject_kind=paper_listing`이면 `subject_id`가 `claim_id`; `subject_kind=offering`이면 개설 ID; `lab`이면 임시 연구실 ID. `uses/develops/studies`는 연구실·논문 수록 근거만, `teaches`는 과목 개설만 허용 |
| `recommendation_evidence` | `recommendation_evidence_id`, `lab_id`, `course_id`, `research_assertion_id`, `research_evidence_scope`, `paper_listing_claim_id`, `course_assertion_id`, `concept_sense_id`, `link_type`, `decision_state`, `rule_version`, `rank_score`, `score_components` | 연구측 assertion은 `lab` 또는 `paper_listing` 주체다. 논문 주체이면 `paper_listing_claim_id`가 그 assertion의 `subject_id`와 같고 해당 claim이 `lab_id`에 연결돼야 한다. 연구실 주체이면 claim ID는 null. 양쪽 뜻 ID와 출처 FK가 해소돼야 연결 가능 |
| `lab_discovery_evidence` | `discovery_evidence_id`, `lab_id`, `research_assertion_id`, `research_evidence_scope`, `paper_listing_claim_id`, `concept_sense_id`, `discovery_type`, `decision_state`, `rule_version` | `discovery_type`은 `domain`, `problem`, `material`; 과목 FK가 없고 준비 과목 점수로 승격하지 않음. 연구측 claim·scope 검사는 `recommendation_evidence`와 동일 |
| `query_intent` | `query_id`, `raw_text`, `positive_phrases`, `negative_phrases`, `ambiguous`, `decision_state`, `interpreter_version` | 각 구절은 원문 `[start,end)`와 정규화 텍스트를 함께 둠. 긍정 구절이 없거나 부정 신호 파싱에 실패하면 자동 순위를 보류 |

`paper_listing` assertion은 “그 목록에 수록된 논문이 이 방법을 사용/개발/연구했다”는 좁은 주장을 뜻한다. 해당 교수 연구실이 현재 같은 방법을 사용한다고 자동 승격하지 않는다. `research_evidence_scope`는 `lab_direct` 또는 `listed_paper`이며 assertion 주체와 정확히 일치해야 한다. `recommendation_evidence.link_type`은 `direct_method`, `direct_tool`만 허용한다. 연구 주제 발견의 도메인·문제·재료 관계는 과목 FK가 없는 `lab_discovery_evidence`에 저장한다. `assertion.review_status`는 `unreviewed`, `accepted`, `rejected`, `ambiguous` 중 하나이며 `assertion_origin`은 `source_explicit`, `automatic_candidate`, `human_reviewed` 중 하나다. 자동 추출 후보는 검토 전 확정 사실로 표시하지 않는다.

`recommendation_evidence.decision_state`는 `eligible_unranked`, `scored`, `insufficient_evidence`, `not_applicable` 중 하나다. 양쪽 검토된 assertion·같은 뜻 ID·정확한 출처가 있어야 `eligible_unranked`가 된다. `scored`는 별도 검증한 순위기가 적용된 경우에만 허용하며 `rank_score`와 `score_components`를 함께 저장한다. 나머지 상태에서는 두 필드가 null이다. `score_components`는 `retrieval_score`, `rule_adjustment`, `dedup_adjustment`, `ranker_version`, `calibration_version`을 명시하고 최종 `rank_score`의 범위·집계식·가중치는 해당 검증된 `ranker_version` 계약에 묶는다. 현재 동결 0.08 가산은 제품용 검증 가중치가 아니므로 이 문서에서 값을 확정하지 않는다.

`lab_discovery_evidence.decision_state`는 `matched`, `insufficient_evidence`, `not_applicable` 중 하나다. `matched`는 검토된 연구측 assertion·출처·뜻이 확인돼 연구실 발견의 설명 근거로 쓸 수 있다는 뜻이며, 과목 준비도나 순위 점수를 뜻하지 않는다.

구현 validator는 `recommendation_evidence`의 연구측 predicate가 `uses` 또는 `develops`, 과목측 predicate가 `teaches`, 양쪽 개념 타입이 `link_type`의 method/tool과 일치함을 확인한다. `lab_discovery_evidence`는 연구측 predicate가 `studies`이고 개념 타입이 `discovery_type`과 일치해야 한다.

`assertion_origin=automatic_candidate`는 최초 `review_status=unreviewed`로만 생성한다. 자동 후보가 `accepted`, `rejected`, `ambiguous`로 바뀌면 `review_actor_id`, `reviewed_at`, `review_protocol_version`을 필수로 남긴다. `assertion_origin=human_reviewed`는 같은 검토 메타데이터와 `accepted`, `rejected`, `ambiguous` 상태만 허용한다. `source_explicit`도 원문에 명시된 주장이라는 출처 성격만 뜻하며, 검토 없이 자동으로 `accepted`가 되지 않는다. `not_applicable`은 확인된 타입·관계 제약상 이 연결에 쓰면 안 되는 경우(예: `studies`를 준비 과목 연결에 투입)를 뜻한다. `insufficient_evidence`는 가능한 관계이지만 출처·뜻·검토가 불충분해 아직 판단할 수 없는 경우다. 새 근거가 들어오면 후자는 재평가할 수 있으며, 전자는 규칙 버전이나 연결 유형을 바꿔야 재평가한다. 모든 상태 전환은 이전 상태·사유·시각·규칙 버전을 감사 기록에 남긴다.

뜻 분리의 우선 검토 예시는 논문 작성의 `logic`과 회로 논리, 테라헤르츠파의 `manipulation`과 로봇 조작이다. 이 예시들은 보류 결과를 본 뒤 찾은 오류이므로 동결 v15의 같은 보류 집합에서 가중치를 다시 맞춰 개선을 주장하지 않는다. 별도 개발 자료에서 뜻 ID와 문맥 제약을 만든 다음 새로운 보류 집합으로 검증한다.

값의 상태는 원본의 각 `(entity_id, field_path)`에 `value_state`로 붙여 `present`, `source_blank`, `source_missing`, `explicit_none`, `not_checked` 중 하나로 저장한다. `present`는 원문 값이 있을 때, `source_blank`는 키는 있으나 빈 값일 때, `source_missing`은 키가 없을 때, `explicit_none`은 출처가 없음을 명시할 때, `not_checked`는 수집·대조를 수행하지 않았을 때만 허용한다. `source_evidence` span은 `present` 필드에만 연결한다. 결측을 0점으로 넣지 않는다. 같은 내용 후보가 상위 목록의 여러 칸을 차지하는 경우에는 코드 병합을 확정하지 않고 `content_group_candidate`로 표시·검토한다. BGE 상위 5개에서 정확히 동일한 제목·교육 본문 후보의 중복은 기본 순위 75/136행(104중복 슬롯), 규칙 가산 순위 73/136행(108중복 슬롯)이었다. 한 과목에서 설명과 학습목표가 동일하면 독립 근거로 두 번 세지 않는다. 한 연구실에 논문이 여러 편이라도 같은 주장의 점수를 무한 누적하지 않는다.

## 2. 규칙 엔진의 역할

### 실제로 사용할 정보의 우선순위

| 입력 근거 | 활용 | 주의 |
|---|---|---|
| 연구실 소개에서 연구실 자신이 방법·도구를 사용/개발한다는 문장 | 직접 관계 후보의 연구실측 강한 근거 | 모집·메뉴·인용 논문 제목을 자기 행위로 오인하지 않음 |
| 첫 다섯 대표 논문의 제목과 초록 | 논문별 연구 행위·대상 확인 | 논문 수록과 연구실 현재 역량은 별개; 초록 없는 제목만으로 직접 기술 사용을 단정하지 않음 |
| 과목 설명과 진도계획 | 실제로 가르치는 방법·도구 확인 | 학습목표가 설명 복사본이면 중복 가산하지 않음; 한 진도 구간은 반복 근거보다 약함 |
| 과목 제목 | 후보 검색과 개념 범위 힌트 | 제목만으로 준비 기술·선수 요건을 확정하지 않음 |
| 선수사항 원문 | 코드·지식의 원문 언급 및 검토 큐 | `권장`, `필수 아님`, 선택 관계를 자동 필수 선수로 승격하지 않음 |
| 사이트/교수 논문 목록 | 출처별 수록 주장과 근거 탐색 | 대표성·현재 연구실 소속 검증 전 추천 강한 근거로 사용하지 않음 |

상위 다섯 대표 논문이라는 창은 이번 실험에서 사용한 고정 범위다. 서비스의 최적 창 길이라는 증거는 아니다. 연구실 소개·논문·과목 계획의 질을 근거 종류별로 기록하고, 단순 텍스트 길이만 신뢰도로 쓰지 않는다.

1. **연구실 탐색과 준비 과목 추천을 다른 관계로 모델링한다.** `studies domain/problem/material`은 연구실 검색·필터에 쓰되, 주제가 겹친다는 이유만으로 준비 과목 점수를 주지 않는다.
2. 준비 과목의 직접 근거 후보는 연구실/논문의 `uses`·`develops` 방법·도구와 과목의 `teaches` 방법·도구가 **같은 뜻 ID**로 이어지는 경우다. 개발 행위는 사용 행위와 구별하고, 제목 한 줄이나 진도 한 구간만의 근거는 낮은 신뢰 상태로 둔다.
3. 다의어는 원문 주변 문맥, 대상 객체, 분야 제약을 검사하고 뜻을 결정할 수 없으면 `insufficient_evidence`로 보류한다. 원문 근거가 없거나 수록 논문이라는 사실만 있는 경우에도 자동 연결하지 않는다.
4. **직접 규칙 B1만으로 목록을 만들지 않는다.** 적격 보류 136행 중 79행에서 빈 목록이었고 고정 5칸 효용이 기존 확장 어휘 기준선보다 두 심사위원 모두에서 낮았다. 넓은 후보 검색과 증거 검사 단계를 분리한다. BGE-M3 순위를 쓰는 모델 추론은 Kaggle GPU에서만 실행·갱신한다.
5. 동결 B1의 0.08 가산은 BGE 상위 1개에서 두 심사위원 모두 명확한 이익을 확인하지 못했다. 이 값을 제품 가중치로 채택하지 않는다. 규칙은 우선 근거 표시·거짓 연결 차단·후보 검토 큐에 쓰고, 순위 가중치는 새 개발 자료와 별도 보류 자료에서 검증 후 정한다.
6. 결과 문장은 원문을 인용해도 자동으로 충실하지 않다. 과목 제목만으로 준비 기술을 단정하지 않고, 주장별 원문 span과 판정 상태를 보여 준다. 근거 부족인 쌍은 이유 문장을 생성하지 않는다.

### 판정 규칙의 실행 순서

아래 순서는 목표 계약의 결정적 판정 절차다. 순위 가중치나 학생 대상 성능이 검증됐다는 뜻은 아니다.

1. 질의에서 원문 span이 있는 긍정·부정 구절을 추출한다. 긍정 구절이 없거나 부정 해석이 모호하면 `query_intent.decision_state=insufficient_evidence`로 둔다.
2. 긍정 관심으로 연구실 발견 후보를 검색한다. `studies` 도메인·문제 관계는 발견 이유로 보존하되 준비 과목 관계로 변환하지 않는다. 명시적 부정 뜻과 충돌하는 후보는 안전성 검토 대상으로 표시한다.
3. 각 후보 연구실의 `uses`·`develops` 방법·도구 주장을 원문 출처와 검토 상태에 묶고, 과목의 `teaches` 주장과 `concept_sense_id`가 같은 연결만 직접 준비 과목 후보로 만든다. 논문 수록 주장은 논문 수준의 행위임을 결과에도 유지한다.
4. 양쪽 출처가 정확한 원문 span으로 확인되고 뜻·행위 주체가 명확한 경우만 `recommendation_evidence.decision_state=eligible_unranked`로 둔다. 검증된 순위기가 적용된 연결만 `scored`로 바꾼다. 제목만의 일치, 다의어 충돌, 출처 미확인, 자동 추출 후보만 남은 경우는 `insufficient_evidence`로 보류한다.
5. 검증된 연결마다 양쪽 `assertion_id`와 인용 span을 하나의 설명에 연결한다. 복사된 교육 본문과 같은 논문의 반복 수록은 독립 근거로 누적하지 않는다. 동일 내용 과목 코드는 합치지 않고 표시 중복 후보로 검토한다.
6. 검색 후보의 표시 순서는 별도 검증한 검색 점수로 정한다. B1 직접 관계만으로 목록을 자르거나 동결 0.08을 가산하지 않는다. 근거가 없는 후보는 준비 과목으로 설명하지 않고, 근거가 부족한 경우 그 상태를 명시한다.

## 3. 현재 구현과 검증 경계

`normalize.py`의 staging v2는 논문 목록 주장 37,417건과 원문 근거 48,645건의 ID·소유 외래 키·원문 span을 구현했다. `validate_staging.py`와 `results/staging_v2_validation.json`에서 전 건의 원문 일치를 확인했다. `concept_sense`, 상태값 전부, 연결 assertion의 외래 키, 실제 서비스 `recommendation_evidence`는 아직 구현하지 않았다. 따라서 이 결정안을 곧바로 서비스 스키마가 완성됐다고 해석하지 않는다.

적격성 조건은 과목 941행, 연구실 203교수 행의 **정보량 프록시**다. 연구실 공유 근거 156구성요소 중 보류 137, 평가 추출 112구성요소/136교수 행을 썼다. 112는 이항 비율 하나의 유한모집단 보정 ±약 4%p 수준을 목표로 한 단순무작위 설계이며 짝차이·희귀 오류의 ±4%p 보장이 아니다. 적격하지 않은 행이나 실사용자 질의에 실험 결론을 일반화하지 않는다.

두 Luna의 910쌍 관계 판정은 B1 단독 추천의 낮은 적용 범위를 확인했다. Kaggle BGE 상위 1개와 사후 상위 5개 비교는 고정 0.08 규칙 가산의 일관된 효용 개선을 확인하지 못했다. 상위 5개 신규 562쌍의 두 Luna 관련도 완전 일치는 58.2%로 낮아 심사별 결과를 분리해 해석한다. 27쌍 이유 문장 파일럿은 인용형 문장의 일관된 충실도 개선을 보이지 않았다. 같은 문장을 재표시한 27카드 A/B 파일럿에서는 두 Luna가 인용형을 더 자주 골랐지만 근거 밖 주장 표시는 줄지 않았고 학생 선호를 측정하지 않았다. 질의 이해 작성 챌린지셋은 Q1의 제한적 개선을 보였으나 두 심사위원 모두 목표 파일을 사전에 봤다. 합성 제거 관문 시험에서는 6위 유입 중 무관 과목이 두 심사위원에서 약 25~32%였고, 처음 다섯 과목에만 자격을 주면 새 유입은 구조적으로 사라지지만 목록이 짧아졌다. 이는 실제 사용자 피드백의 효과를 검증한 수치가 아니다. 이 데이터 모델은 그런 실패와 불확실성을 **표현할 수 있도록** 정한 것이며 추천 성능 달성을 보증하는 계약이 아니다.
