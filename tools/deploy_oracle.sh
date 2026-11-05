#!/usr/bin/env bash
# 개발 VM → Oracle 서버 배포. 사용: tools/deploy_oracle.sh [ssh 호스트 별칭, 기본 oracle-micro]
# 코드(curri/)와 새 정제 앱 데이터만 올린다. 서버 DB(~/app/.local)는 보존한다.
set -euo pipefail
HOST="${1:-oracle-micro}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="data/sunwoo"

ssh "$HOST" "mkdir -p ~/app/.local ~/app/$DATA; if [ -d ~/app/curri ]; then rm -r -- ~/app/curri; fi"
tar -C "$ROOT" --exclude='__pycache__' -cf - curri \
  "$DATA/app_profiles.jsonl" "$DATA/labs.jsonl" "$DATA/courses.jsonl" \
  "$DATA/papers.jsonl" "$DATA/lab_course_bge_m3.json" \
  "$DATA/concepts.json" "$DATA/legacy_lab_aliases.json" | ssh "$HOST" 'tar -C ~/app -xf -'
ssh "$HOST" 'if [ -d ~/app/data/sunwoo/legacy ]; then rm -r -- ~/app/data/sunwoo/legacy; fi; if [ -e ~/app/.local/doc_embeddings.npz ]; then rm -- ~/app/.local/doc_embeddings.npz; fi'
scp -q "$ROOT/tools/deploy/curri.service" "$HOST:/tmp/curri.service"
ssh "$HOST" 'sudo install -m 644 /tmp/curri.service /etc/systemd/system/curri.service \
  && sudo systemctl daemon-reload && sudo systemctl enable curri >/dev/null 2>&1 \
  && sudo systemctl restart curri && sleep 2 && systemctl is-active curri'
