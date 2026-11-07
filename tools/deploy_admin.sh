#!/usr/bin/env bash
# 관리자 VM 설치. 사용: tools/deploy_admin.sh <관리자 VM ssh 별칭> [서비스 서버 별칭, 기본 oracle-micro]
# 이 개발 VM에서 두 서버 모두 ssh로 접속할 수 있어야 한다.
#  - 서비스 서버에 관리자 토큰(.local/admin_token)을 만들고, 관리자 VM 전용 SSH 키를 '포트 전달 하나만 가능'으로 등록한다.
#  - 관리자 VM에 콘솔(127.0.0.1:8300), 터널(127.0.0.1:18200 → 서비스 127.0.0.1:8200), 매일 백업 타이머를 설치한다.
#  - 콘솔은 공개 포트를 열지 않는다. 접속: ssh -L 8300:127.0.0.1:8300 <관리자 VM> 후 http://127.0.0.1:8300
set -euo pipefail
ADMIN="${1:?관리자 VM ssh 별칭을 주세요}"
MAIN="${2:-oracle-micro}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAIN_ADDR=$(ssh -G "$MAIN" | awk '/^hostname /{print $2}')
MAIN_USER=$(ssh -G "$MAIN" | awk '/^user /{print $2}')

# 1) 서비스 서버의 관리자 토큰 (새로 만들었으면 서비스를 재시작해 읽게 한다)
CREATED=$(ssh "$MAIN" 'f=~/app/.local/admin_token; if [ -s "$f" ]; then echo 0; else mkdir -p ~/app/.local; python3 -c "import secrets;print(secrets.token_urlsafe(32))" > "$f"; chmod 600 "$f"; echo 1; fi')
TOKEN=$(ssh "$MAIN" 'cat ~/app/.local/admin_token')
if [ "$CREATED" = 1 ]; then ssh "$MAIN" 'sudo systemctl restart curri && sleep 2 && systemctl is-active curri'; fi

# 2) 관리자 VM 파일
AUSER=$(ssh "$ADMIN" whoami)
AHOME=$(ssh "$ADMIN" 'echo $HOME')
ssh "$ADMIN" 'mkdir -p ~/curri-admin/static ~/curri-admin/backups ~/.ssh && chmod 700 ~/curri-admin/backups'
scp -q "$ROOT/tools/admin/admin_server.py" "$ADMIN:curri-admin/admin_server.py"
scp -q "$ROOT"/tools/admin/static/* "$ADMIN:curri-admin/static/"
ssh "$ADMIN" "cd ~/curri-admin && TOKEN='$TOKEN' python3 -c '
import json, os, pathlib
p = pathlib.Path(\"admin.json\")
cfg = json.loads(p.read_text()) if p.exists() else {\"users\": {}}
cfg.update(main_url=\"http://127.0.0.1:18200\", token=os.environ[\"TOKEN\"], port=cfg.get(\"port\", 8300))
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1)); p.chmod(0o600)'"

# 3) 터널 전용 키: 서비스 서버에서는 127.0.0.1:8200 포트 전달만 허용
PUB=$(ssh "$ADMIN" 'test -f ~/.ssh/curri_tunnel || ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/curri_tunnel -C curri-admin-tunnel; cat ~/.ssh/curri_tunnel.pub')
KEY=$(echo "$PUB" | awk '{print $2}')
ssh "$MAIN" "mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && (grep -qF '$KEY' ~/.ssh/authorized_keys || echo 'restrict,port-forwarding,permitopen=\"127.0.0.1:8200\",command=\"/bin/false\" $PUB' >> ~/.ssh/authorized_keys)"
ssh "$ADMIN" "ssh-keygen -F '$MAIN_ADDR' >/dev/null || ssh-keyscan -H '$MAIN_ADDR' >> ~/.ssh/known_hosts 2>/dev/null"

# 4) systemd: 터널, 콘솔, 매일 백업
cat > /tmp/curri-admin-tunnel.service <<UNIT
[Unit]
Description=3분커리 관리자 터널 (서비스 서버 관리자 API)
After=network-online.target
Wants=network-online.target
[Service]
User=$AUSER
ExecStart=/usr/bin/ssh -N -i $AHOME/.ssh/curri_tunnel -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes -L 127.0.0.1:18200:127.0.0.1:8200 $MAIN_USER@$MAIN_ADDR
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
cat > /tmp/curri-admin.service <<UNIT
[Unit]
Description=3분커리 관리자 콘솔 (127.0.0.1:8300)
After=curri-admin-tunnel.service
[Service]
User=$AUSER
WorkingDirectory=$AHOME/curri-admin
ExecStart=/usr/bin/python3 $AHOME/curri-admin/admin_server.py serve
Restart=on-failure
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
cat > /tmp/curri-admin-backup.service <<UNIT
[Unit]
Description=3분커리 서비스 DB를 관리자 VM으로 백업 (30일 보관)
[Service]
Type=oneshot
User=$AUSER
ExecStart=/usr/bin/python3 $AHOME/curri-admin/admin_server.py backup 30
UNIT
cat > /tmp/curri-admin-backup.timer <<UNIT
[Unit]
Description=3분커리 관리자 VM 매일 백업 (05:00 KST)
[Timer]
OnCalendar=*-*-* 20:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
UNIT
scp -q /tmp/curri-admin-tunnel.service /tmp/curri-admin.service /tmp/curri-admin-backup.service /tmp/curri-admin-backup.timer "$ADMIN:/tmp/"
ssh "$ADMIN" 'sudo install -m 644 /tmp/curri-admin-tunnel.service /tmp/curri-admin.service /tmp/curri-admin-backup.service /tmp/curri-admin-backup.timer /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl enable --now curri-admin-tunnel curri-admin curri-admin-backup.timer >/dev/null 2>&1 \
  && sleep 3 && systemctl is-active curri-admin-tunnel curri-admin'
ssh "$ADMIN" 'python3 ~/curri-admin/admin_server.py backup 30'
echo "설치 완료. 관리자 계정 만들기: ssh -t $ADMIN python3 ~/curri-admin/admin_server.py adduser <이름>"
echo "접속: ssh -L 8300:127.0.0.1:8300 $ADMIN  →  http://127.0.0.1:8300"
