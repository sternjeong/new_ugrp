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
  "$DATA/papers.jsonl" "$DATA/suspect_papers.json" "$DATA/lab_course_bge_m3.json" \
  "$DATA/concepts.json" "$DATA/legacy_lab_aliases.json" | ssh "$HOST" 'tar -C ~/app -xf -'
ssh "$HOST" 'if [ -d ~/app/data/sunwoo/legacy ]; then rm -r -- ~/app/data/sunwoo/legacy; fi; if [ -e ~/app/.local/doc_embeddings.npz ]; then rm -- ~/app/.local/doc_embeddings.npz; fi'
ssh "$HOST" "mkdir -p ~/app/tools ~/app/.local/backups"
scp -q "$ROOT/tools/backup_db.py" "$HOST:app/tools/backup_db.py"
scp -q "$ROOT/tools/deploy/curri.service" "$ROOT/tools/deploy/curri-backup.service" "$ROOT/tools/deploy/curri-backup.timer" "$HOST:/tmp/"
# 배포 직전 백업: 시작 시 마이그레이션이 DB를 바꿀 수 있다.
ssh "$HOST" 'test ! -f ~/app/.local/curri.sqlite || python3 ~/app/tools/backup_db.py ~/app/.local/curri.sqlite ~/app/.local/backups 14 >/dev/null'
ssh "$HOST" 'sudo install -m 644 /tmp/curri.service /tmp/curri-backup.service /tmp/curri-backup.timer /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl enable curri >/dev/null 2>&1 \
  && sudo systemctl enable --now curri-backup.timer >/dev/null 2>&1 \
  && sudo systemctl restart curri && sleep 2 && systemctl is-active curri'
