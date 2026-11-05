# sunwoo 브랜치 데이터 반입 기록

- 원격: `https://github.com/sunwoochoi2002/2026-UGRP.git`
- 브랜치: `sunwoo`
- 커밋: `0fa6c47aa4511b5a6db5edc424064109e9e957f9`
- 반입 범위: 해당 커밋의 `data/` 아래 파일 26개 전부, 총 42,212,799바이트
- 검증: [`IMPORT_MANIFEST.json`](IMPORT_MANIFEST.json)에 각 파일의 SHA-256과 크기를 기록했다. 모든 JSON/JSONL을 파싱하고 해시를 대조했다.

이 폴더는 원격 데이터의 **그대로 보관한 스냅샷**이다. 원격의 [`README.md`](README.md)는 해당 브랜치의 데이터 계약이며, 이 저장소의 앱 코드가 그 계약으로 전환됐다는 뜻은 아니다. 현재 앱용 `data/courses.jsonl`·`data/labs.jsonl` 및 루트 `final_courses.jsonl`·`final_labs.jsonl`은 변경하지 않았다. 이름이 같은 파일끼리 해시가 다르므로 기존 추천 실험의 입력을 이 스냅샷으로 바꾸려면 별도 마이그레이션과 재평가가 필요하다.

주요 자료는 최종 원자료 `final_courses.jsonl`·`final_labs.jsonl`, 정제본 `courses.jsonl`·`labs.jsonl`, 대표 논문 `papers.jsonl`, 연구센터 `research_centers.jsonl`, 검증·정제 기록 `curation/`, 과거 MVP `legacy/mvp-4dept/`다.
