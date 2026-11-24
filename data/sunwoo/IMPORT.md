# sunwoo 정제 데이터 반입 기록 (2026-11-13)

- 서비스 기준: final `e2cd1b42977de5108b9f79e4831d55b2e995810c`
- 데이터 기준: sunwoo `5159843302a8e698110cd3060cde0c29dfa8943e`
- 대응: 원본 `data/<path>` → 서비스 `data/sunwoo/<path>`
- 범위: JSON/JSONL 24파일. 20개는 기존과 동일, 3개는 교체(`labs.jsonl`, `papers.jsonl`, `curation/lab_overrides.json`), 1개는 추가(`curation/paper_identity.jsonl`).
- 출처: https://github.com/sunwoochoi2002/2026-UGRP.git
- 파일 크기·SHA-256: [IMPORT_MANIFEST.json](IMPORT_MANIFEST.json). 새 데이터도 원본 커밋과 바이트 단위로 같다.

## 파생 자료

박성우(`0a6ff7bc33b7ed4911d691f6ab0c5136`)·최영준(`f99a04f1c7ba3fe4f420c343e9c9a1ca`)의 원본이 달라졌다. `tools/build_curated_profiles.py`를 새 labs/papers로 임시 폴더에서 실행한 뒤 이 두 ID의 레코드만 app_profiles에 반영했다. 나머지 305개 레코드는 줄 끝까지 기존 바이트를 보존했다. 전체 생성기를 서비스 폴더에 바로 실행하면 별도의 교수 영문 이름 보완 2건도 반영되므로 이번 통합에서는 그렇게 하지 않았다.

과목 파일은 동일하고 유사도는 연구실별 독립 계산이므로, 프로필이 같은 305곳의 기존 점수는 유지한다. 바뀐 두 곳의 점수는 제거했다. `lab_course_bge_m3.json`의 `migration`에는 이전 입력 해시, 그대로 유지한 프로필 행별 해시, 재계산할 ID를 남겼다. `sources`는 이 부분 재사용 결과에 대응하는 현재 입력의 해시이며 전체를 재임베딩했다는 뜻이 아니다.

final 고유 concepts·legacy_lab_aliases·suspect_papers는 바이트 단위로 보존했다. suspect 판정 기록을 새로 계산하거나 새 논문의 검증으로 간주하지 않는다.

## 반입 뒤 수정 (2026-11-24)

박성우(`0a6ff7bc33b7ed4911d691f6ab0c5136`)의 논문을 다시 검증했다. 남아 있던 4편은 모두 다른 사람의 논문이어서 제외했고, 본인 논문 2편(ETRI Journal 2025, POPL 2014)을 허용 목록으로 넣었다. 여러 사람이 합쳐진 저자 프로필 A5100324409는 `author_ids`에서 뺐다. 최영준은 공식 목록 7편이 그대로임을 다시 확인했고 데이터는 바꾸지 않았다. 근거와 절차는 [논문 귀속 검증](../../docs/analysis/PAPER_ATTRIBUTION_REVIEW.md), 사례는 [사례집](curation/CASES.md) D-19~D-23.

- 바뀐 파일: `curation/lab_overrides.json`, `labs.jsonl`·`papers.jsonl`·`app_profiles.jsonl`의 박성우 줄, `lab_course_bge_m3.json`의 프로필 해시. 다른 연구실 줄은 바이트 그대로다. 논문 연결은 2,763 → 2,761개.
- `IMPORT_MANIFEST.json`의 `files`는 반입 당시 해시이고, 그 뒤 고친 파일의 현재 해시는 `corrected_files`, 이력은 `corrections`에 있다.
- 추가: `curation/paper_attribution_audit.json`(검토 대기열).
- 다시 만들 외부 자료는 아래와 같다. 박성우·최영준 두 곳의 프로필 주제 수와 내용이 워커 쪽 사본과 다르다.

## 외부 워커를 다시 연결하기 전

코드와 외부 워커 프로토콜은 final 그대로다. 따라서 옛 워커 응답을 자동으로 차단하는 버전 검사는 없다.

1. 서비스·임베딩 워커를 멈추고 DB를 백업한다.
2. 워커에 현재 app_profiles와 courses를 반영하고 `tools/embed_worker/precompute.py`로 doc_embeddings와 전체 과목 유사도를 재생성한다.
3. 검색 조각 원본도 현재 labs/papers로 다시 만든 뒤 search_chunks·search_vectors를 재생성한다. 예전 vectorRAG 묶음을 그대로 넣으면 제거한 논문이 되살아날 수 있다. `tools/embed_worker/build_search_assets.py`는 연구실 묶음에 없는 논문 조각을 빼므로 예전 묶음으로 만들어도 제거한 논문은 들어가지 않는다. 다만 새로 넣은 논문(박성우 2편, 최영준 7편)의 조각은 묶음을 다시 만들어야 생긴다.
4. 서버 DB의 `phrase_sims` 캐시를 비우고 서버를 재시작한다. 연구실 요약(공유 요약)은 검토된 연구실의 캐시 키가 논문에 따라 바뀌므로 그 연구실만 자동으로 새로 만든다(`ResearchGuide.summary_key`). 기존 AI 가이드와 저장 결과는 과거 데이터로 생성되었음을 구분한다.
5. 새 자산을 가진 워커만 연결하고 검색·근거·과목을 검증한다. 갱신 전에는 worker_token을 연결하지 않고 사전 검색을 사용한다.

이번 작업에서는 외부 서버·Kaggle 데이터셋을 변경하지 않았다. 로컬 검증은 새 DB와 워커 미연결 상태에서 수행한다. 기존 sunwoo DB(`curri-full.sqlite`)는 그대로 보존한다.
