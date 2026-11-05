# 서비스 코드 작업의 기본 맥락

현재 서비스 골격은 저장소 루트의 `curri/`(코드), `data/`(앱 데이터), `tests/`, `tools/`다. `data/raw/`는 앱 변환 전 원자료, `experiments/`는 앱에 반영하지 않은 실험, `archive/legacy_demo/`는 이전 정적 데모다. 2026-10-08에 기존 `2026-UGRP-sunwoo/` 폴더 내용을 루트로 옮겼다.

코드 작업을 시작할 때 `docs/analysis/SERVICE_CODEBASE_ANALYSIS.md`를 먼저 읽고, 작업과 관련된 `docs/product/PRODUCT_PLAN.md` 및 실제 구현을 확인한다. 최신 사용자 지시는 기존 분석과 기획보다 우선한다.

분석 문서는 현재 제품 흐름, 화면·API·데이터·저장 책임, 구현된 기능과 후속 기능, 설문과 앱의 차이를 정리한다. 제품 정책이나 구조가 바뀌면 해당 문서도 갱신한다.

연구실·교과목·논문 데이터 및 추천 작업에서는 `docs/analysis/RECOMMENDATION_DATASET_ANALYSIS.md`도 읽는다. 새 원자료와 앱 변환자료의 대응, 복합 과목 코드, 논문 출처·연구실 연결과 원문/추론 구분을 확인한다.
