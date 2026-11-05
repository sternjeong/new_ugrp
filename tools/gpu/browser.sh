#!/usr/bin/env bash
# VM 안의 크롬(Chromium)을 Xvfb 가상 화면에 띄우고 noVNC로 내보낸다. 모든 포트는 localhost 전용이며
# 관제 센터가 /browser/ 경로로 프록시하므로 SSH 터널 하나로 접속한다. 이미 떠 있는 것은 건드리지 않는다.
set -u
DISP="${BROWSER_DISPLAY:-:99}"
PROFILE="${BROWSER_PROFILE:-$HOME/browser-vm/profile}"   # 로그인·확장 프로그램이 유지되는 프로필
CHROME="${CHROME_BIN:-$(ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | tail -1)}"
CHROME="${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}"
export DISPLAY="$DISP"
mkdir -p "$PROFILE"

pgrep -f "Xvfb $DISP" >/dev/null || { nohup Xvfb "$DISP" -screen 0 1600x1000x24 >/dev/null 2>&1 & sleep 1; }
pgrep -x openbox >/dev/null || { nohup openbox >/dev/null 2>&1 & }
pgrep -f "x11vnc.*-rfbport 5900" >/dev/null ||
  x11vnc -display "$DISP" -nopw -localhost -rfbport 5900 -forever -shared -bg -q -o /dev/null >/dev/null 2>&1
pgrep -f "websockify.*6080" >/dev/null ||
  { nohup websockify --web /usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900 >/dev/null 2>&1 & }
if ! pgrep -f "remote-debugging-port=9222" >/dev/null; then
  [ -x "$CHROME" ] || { echo "크롬 실행 파일을 찾을 수 없습니다 (npx playwright install chromium)"; exit 1; }
  nohup "$CHROME" --no-sandbox --user-data-dir="$PROFILE" --no-first-run --lang=ko-KR \
    --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
    --start-maximized chrome://extensions >/dev/null 2>&1 &
fi
sleep 1
echo ok
