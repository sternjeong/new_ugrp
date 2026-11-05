# 3분커리 데이터 위치

현재 작업 폴더의 데이터 원본은 [`sunwoo/`](sunwoo/IMPORT.md) 한 곳에 모았다. 외부 저장소 `sunwoo` 브랜치의 `data/` 26파일을 가져온 스냅샷이며, 파일별 출처와 SHA-256은 [`IMPORT_MANIFEST.json`](sunwoo/IMPORT_MANIFEST.json)에 있다.

| 위치 | 용도 |
|---|---|
| `sunwoo/final_courses.jsonl`, `sunwoo/final_labs.jsonl` | 해당 브랜치의 최신 최종 원자료 |
| `sunwoo/courses.jsonl`, `sunwoo/labs.jsonl`, `sunwoo/papers.jsonl`, `sunwoo/research_centers.jsonl` | 정제본과 연결 자료 |
| `sunwoo/curation/` | 정제·검증 기록 |
| `sunwoo/legacy/mvp-4dept/` | **현재 `curri/` 앱이 기본으로 읽는** 기존 4개 학과 MVP 형식 |

정제본과 앱용 MVP는 스키마가 다르다. `curri/`가 정제본을 자동으로 읽는 것은 아니다. 앱 실행 시 `--data-dir`을 생략하면 `sunwoo/legacy/mvp-4dept/`를 사용한다. `--data-dir`에는 현재 엔진과 호환되는 형식의 폴더를 지정해야 한다.

이전 루트 `final_*.jsonl`, `data/*.jsonl`, `data/raw/`는 중복·충돌을 피하려는 사용자 요청에 따라 2026-10-31에 제거했다. 삭제 전 복사본은 작업 폴더 밖 `/home/ubuntu/.local/share/new_ugrp_pre_sunwoo_cleanup_20261031.tar.gz`에 보관했다. 기존 실험의 해시와 결과 문서는 당시 입력 스냅샷의 기록으로 읽는다.
