#!/usr/bin/env bash
# 서버(ugrp) 안에서 한 번만 실행하는 HTTPS 설정. 사용(개발 VM에서):
#   scp tools/deploy/Caddyfile oracle-micro:/tmp/Caddyfile
#   ssh oracle-micro 'bash -s' < tools/deploy/setup_https.sh
# 선행 조건: DuckDNS의 3mincurri가 이 서버 공인 IP를 가리키고, OCI 보안 목록에서 80·443이 열려 있어야 한다.
set -euo pipefail

echo "[1/4] 방화벽: 80, 443 허용(재부팅 후에도 유지)"
sudo iptables -C INPUT -p tcp -m multiport --dports 80,443 -m state --state NEW -j ACCEPT 2>/dev/null \
  || sudo iptables -I INPUT 5 -p tcp -m multiport --dports 80,443 -m state --state NEW -j ACCEPT
sudo netfilter-persistent save >/dev/null

echo "[2/4] Caddy 설치 (공식 저장소)"
sudo apt-get update -qq
sudo apt-get install -y curl gnupg >/dev/null    # Ubuntu 24.04에는 debian-keyring·apt-transport-https가 없고 필요하지도 않다
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y caddy >/dev/null

echo "[3/4] 프록시 설정과 Secure 쿠키"
sudo install -m 644 /tmp/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's|--port 8200$|--port 8200 --secure-cookie|' /etc/systemd/system/curri.service
sudo systemctl daemon-reload
sudo systemctl restart curri
sudo systemctl enable --now caddy
sudo systemctl reload caddy

echo "[4/4] 확인"
sleep 3
systemctl is-active curri caddy
free -m | sed -n 2p
