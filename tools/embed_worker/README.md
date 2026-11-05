# 임베딩 워커 (Kaggle GPU ↔ 서비스 서버)

관심 문장을 bge-m3로 임베딩해 연구실을 찾는 계산을 Kaggle GPU가 맡는다. Kaggle은 외부에서 들어오는 연결을 받을 수 없어서 **워커가 서버로 먼저 접속**한다(서버는 Kaggle 주소를 몰라도 된다).

현재 서비스의 질의 해석 엔진은 좋아하는 구절과 피하고 싶은 구절을 분리하고, 각각의 BGE-M3 연구실 유사도와 사전 검색을 합친다. `precompute_corpus.ipynb`는 새 정제본의 추천 가능 연구실과 과목을 한 번 임베딩해 `doc_embeddings.npz`와 `lab_course_bge_m3.json`을 만든다. 과목 유사도는 학습 후보를 찾는 데만 쓰며 공식 선수과목 근거로 표시하지 않는다.

서비스 서버의 `.local/kaggle_launcher.json`이 있으면 첫 질의로 종료된 Kaggle 워커를 자동 제출하고, 브라우저는 연결을 최대 3분 기다린다. Kaggle 시작 실패나 시간 초과에는 기존 사전 검색을 보여 준다. Kaggle 인증 정보는 서버의 `~/.kaggle/credentials.json`에 권한 600으로 보관한다. 워커는 유휴 10분 또는 실행 상한 60분에 종료되며, Kaggle GPU 주간 한도와 대기열에 따라 시작이 실패할 수 있다.

```
브라우저 → 서버 /api/search → (구절 임베딩 필요) → 서버의 작업 큐
Kaggle 워커 → GET /api/worker/poll (long-poll) → 작업 수신 → bge-m3로 구절×연구실 유사도 계산 → POST /api/worker/answer
서버 ← 유사도 → 사전 검색과 순위 융합(RRF) → 결과
```

워커가 없거나 6초 안에 응답하지 않으면 서버는 **해석을 반영한 사전 검색**으로 후퇴한다(검색은 항상 응답한다).

## 시작·종료

```
gpuhub submit tools/embed_worker/embed_worker.ipynb --timeout-min 60
gpuhub status          # 상태·남은 쿼터
```
- 보통 제출 후 1~2분 안에 서버에 연결된다. `curl https://3mincurri.duckdns.org/api/engine` 이 `{"embedding": true}`면 연결된 것이다.
- **요청이 `idle_exit_min`분(기본 10) 동안 없으면 스스로 종료**하고(GPU 쿼터 절약), 최대 `max_run_min`분 뒤 종료한다. 종료하면 서비스는 자동으로 사전 검색으로 후퇴한다.
- 값은 `.local/worker_config.json`(저장소에 올라가지 않음)에서 바꾼다: `{"base_url", "token", "idle_exit_min", "max_run_min"}`.

## 토큰

- 서버: `~/app/.local/worker_token`(권한 600). 개발 VM: `.local/worker_token`, `.local/worker_config.json`. 모두 `.gitignore` 대상이다.
- 바꾸려면 새 토큰을 두 곳에 같은 값으로 넣고 서버(`sudo systemctl restart curri`)를 재시작한다. 설정 파일은 비공개 Kaggle 데이터셋으로 올라간다.
- 토큰이 없으면 서버는 워커 연동을 끈다(`/api/worker/*`가 404).

## 개인정보

임베딩 요청에는 **사용자가 입력한 관심 문장(해석된 구절)** 이 Kaggle 워커로 전달된다. 서버는 이를 파일에 따로 저장하지 않는다. 사용자 안내 문구에 이 사실을 넣을지 결정해야 한다.

## 로컬 시험

```
PYTHONPATH=. python3 -m unittest tests.test_query_engine          # 엔진·브로커·HTTP (모델 불필요)
PYTHONPATH=. <numpy가 있는 python> -m unittest tests.test_embed_worker   # 워커 프로토콜(가짜 인코더)
```
`test_query_engine`에는 `experiments/query_understanding/V2/sims_v2.json`(모델 실제 유사도)로 실험 순위를 그대로 재현하는 검증이 포함되어 있다.

## 상시 운영 (전용 CPU 서버)

Kaggle은 세션 시간·주당 쿼터 때문에 24시간 상시로 둘 수 없다. 상시 운영은 항상 켜져 있는 서버에서 **같은 워커를 CPU로** 돌린다. 서버로 먼저 접속하는 방식이라 포트를 열 필요가 없고, 워커가 죽으면 서비스는 45초 안에 사전 검색으로 후퇴한다.

- 필요한 서버: ARM A1(무료 한도 2 OCPU·12GB가 남아 있음) 또는 RAM 4GB 이상. 모델 로딩에 약 2.3GB를 쓴다. 이 개발 VM(디스크 99%)은 부적합하다.
- 설치: `.local/worker_config_vm.json`(`idle_exit_min: 0`, `max_run_min: 0`, `doc_cache`)을 두고 `tools/embed_worker/deploy_cpu_worker.sh <ssh 별칭>`.
- 서비스 `curri-embed-worker`가 재부팅 후에도 자동 시작하고, 죽으면 10초 뒤 다시 시작한다. 연구실 문서 임베딩은 첫 실행에 한 번 계산해 `doc_embeddings.npz`에 캐시한다.
- 요청은 한 번에 하나씩 처리한다. 동시에 몰리면 대기열이 생기고 6초를 넘기면 해당 검색만 사전 검색으로 후퇴한다.
