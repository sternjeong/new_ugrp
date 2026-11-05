#!/usr/bin/env bash
# 상시 임베딩 워커를 전용 서버(CPU)에 설치한다. 사용: tools/embed_worker/deploy_cpu_worker.sh <ssh 호스트 별칭>
# 전제: 그 서버에 ubuntu 계정 ssh 접속 가능, 인터넷(PyPI, huggingface.co, 서비스 도메인) 접근 가능.
# 서버에 올라가는 것: worker.py, app_profiles.jsonl, worker_config.json(토큰 포함, 권한 600), systemd 서비스
set -euo pipefail
HOST="${1:?ssh 호스트 별칭을 지정하세요}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$ROOT/.local/worker_config_vm.json"
[ -f "$CONFIG" ] || { echo "$CONFIG 가 없습니다."; exit 1; }

ssh "$HOST" 'mkdir -p ~/embed-worker'
scp -q "$ROOT/tools/embed_worker/worker.py" "$ROOT/data/sunwoo/app_profiles.jsonl" "$ROOT/tools/embed_worker/curri-embed-worker.service" "$HOST:embed-worker/"
ssh "$HOST" 'umask 077 && cat > ~/embed-worker/worker_config.json' < "$CONFIG"

ssh "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
cd ~/embed-worker
echo "[1/3] 파이썬 환경과 패키지"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv >/dev/null
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q torch sentence-transformers numpy
echo "[2/3] 모델 내려받기(bge-m3, 약 2.3GB)"
HF_HOME=$HOME/embed-worker/hf venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3'); print('모델 준비 완료')"
echo "[3/3] 서비스 등록"
sudo install -m 644 curri-embed-worker.service /etc/systemd/system/curri-embed-worker.service
sudo systemctl daemon-reload
sudo systemctl enable curri-embed-worker >/dev/null 2>&1
sudo systemctl restart curri-embed-worker
sleep 5
systemctl is-active curri-embed-worker
free -m | sed -n 2p
REMOTE
