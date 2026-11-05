#!/usr/bin/env bash
# Switch the active guide for future requests without restarting the service.
set -euo pipefail
variant="${1:-}"
host="${2:-oracle-micro}"
if [[ "$variant" != A && "$variant" != B ]]; then
  echo "사용: bash tools/set_guide_variant.sh A|B [ssh-host]" >&2
  exit 1
fi
ssh "$host" "mkdir -p ~/app/.local; tmp=\$(mktemp ~/app/.local/guide_variant.XXXXXX); printf '%s\\n' '$variant' > \"\$tmp\"; mv \"\$tmp\" ~/app/.local/guide_variant; printf '활성 가이드: '; cat ~/app/.local/guide_variant"
