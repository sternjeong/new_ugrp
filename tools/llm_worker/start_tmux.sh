#!/usr/bin/env bash
# AI 연구 가이드·논문 요약 워커를 이 VM의 tmux 세션(curri-llm)으로 띄운다. Claude Code CLI에 로그인돼 있어야 한다(API 키 불필요).
# 사용: tools/llm_worker/start_tmux.sh [서비스 서버 ssh 별칭, 기본 oracle-micro] [서비스 주소, 기본 https://3mincurri.duckdns.org]
set -euo pipefail
MAIN="${1:-oracle-micro}"
BASE="${2:-https://3mincurri.duckdns.org}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CREATED=$(ssh "$MAIN" 'f=~/app/.local/llm_worker_token; if [ -s "$f" ]; then echo 0; else mkdir -p ~/app/.local; python3 -c "import secrets;print(secrets.token_urlsafe(32))" > "$f"; chmod 600 "$f"; echo 1; fi')
TOKEN=$(ssh "$MAIN" 'cat ~/app/.local/llm_worker_token')
if [ "$CREATED" = 1 ]; then ssh "$MAIN" 'sudo systemctl restart curri && sleep 2 && systemctl is-active curri'; fi
mkdir -p "$ROOT/.local"
BASE="$BASE" TOKEN="$TOKEN" python3 -c 'import json,os;print(json.dumps({"base_url":os.environ["BASE"],"token":os.environ["TOKEN"]}))' > "$ROOT/.local/llm_worker.json"
chmod 600 "$ROOT/.local/llm_worker.json"
command -v claude >/dev/null || { echo "claude CLI가 없습니다."; exit 1; }
if tmux has-session -t curri-llm 2>/dev/null; then tmux kill-session -t curri-llm; fi
tmux new-session -d -s curri-llm "cd '$ROOT' && python3 tools/llm_worker/worker.py --config .local/llm_worker.json 2>&1 | tee -a .local/llm_worker.log"
echo "워커 시작: tmux attach -t curri-llm (빠져나오기 Ctrl+B, D)"
