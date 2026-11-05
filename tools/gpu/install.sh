#!/usr/bin/env bash
# 사용자 전역 설치: ~/.gpu-hub 에 kaggle 환경과 앱을 두고 ~/.local/bin/gpuhub 를 만든다.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
HUB="${GPU_HUB_HOME:-$HOME/.gpu-hub}"
mkdir -p "$HUB/app" "$HOME/.local/bin"
[ -x "$HUB/venv/bin/kaggle" ] || { python3 -m venv "$HUB/venv"; "$HUB/venv/bin/pip" install -q kaggle; }
cp "$SRC/gpu_hub.py" "$SRC/dashboard.html" "$SRC/browser.sh" "$HUB/app/"
printf '#!/usr/bin/env bash\nexec "%s/venv/bin/python" "%s/app/gpu_hub.py" "$@"\n' "$HUB" "$HUB" > "$HOME/.local/bin/gpuhub"
chmod +x "$HOME/.local/bin/gpuhub"
echo "설치 완료. 인증: $HUB/venv/bin/kaggle auth login --no-launch-browser"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "PATH에 ~/.local/bin 을 추가하세요.";; esac
