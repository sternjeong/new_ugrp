# 서비스 데이터

2026-11-13 사용자 결정에 따라 코드는 `final` (`e2cd1b4`), 대응하는 정제 데이터는 `sunwoo` (`5159843`)를 기준으로 한다. 앱 기본 경로는 `data/sunwoo/`이다.

| 자료 | 출처·처리 |
|---|---|
| `sunwoo/labs.jsonl` | sunwoo 정제본 그대로: 365개, 추천 가능 307개 |
| `sunwoo/courses.jsonl` | 양쪽 동일: 1,316개, 추천 가능 1,151개 |
| `sunwoo/papers.jsonl` | sunwoo 정제본에서 박성우(2026-11-24), 박상돈·이승우(2026-11-25)를 고침: 307묶음, 논문 연결 2,757개 |
| `sunwoo/curation/`, `final_*.jsonl`, `research_centers.jsonl`, `legacy/mvp-4dept/`의 JSON/JSONL | sunwoo 스냅샷. 과거 paper_identity 검증 기록은 현재 논문 모두의 인증서가 아님 |
| `sunwoo/app_profiles.jsonl` | final 프로필 중 원본이 바뀐 박성우·최영준(2026-11-13, 박성우는 11-24 다시), 박상돈·이승우(2026-11-25) 4곳만 기존 생성기로 갱신. 나머지 303곳 그대로 |
| `sunwoo/curation/paper_attribution_audit.json` | 논문 귀속 검토 대기열(`tools/paper_attribution.py audit --write`). 어디부터 볼지의 목록이며 판정이 아님 |
| `sunwoo/lab_course_bge_m3.json` | 원본이 동일한 303곳의 점수만 재사용. 바뀐 4곳은 재계산 전까지 유사도 없음 |
| `sunwoo/concepts.json`, `legacy_lab_aliases.json`, `suspect_papers.json` | final 고유 데이터 그대로 보존 |

논문 활용 방식과 추천·운영 기능은 final을 따른다. 이는 모든 논문의 저자 신원 검증 완료를 의미하지 않는다. 기존 실험 자료는 당시 입력 기준의 기록이며 최신 데이터로 재평가한 결과가 아니다.

논문과 교수의 연결은 [논문 귀속 검증](../docs/analysis/PAPER_ATTRIBUTION_REVIEW.md) 절차로 검토한다. 서비스가 보여 주는 2,757편 중 사람 검토 23편, 학교 목록·논문 ORCID 확인 2,116편, 미확인 618편이다(2026-11-25). `python3 tools/paper_attribution.py check`가 판정이 모든 파일에 반영됐는지 검사한다.

[반입 기록](sunwoo/IMPORT.md)과 [파일별 출처·해시](sunwoo/IMPORT_MANIFEST.json)가 이번 데이터 통합의 기준이다. 하위 README·사례집의 기존 설명은 과거 수집·정제 당시의 기록이다.
