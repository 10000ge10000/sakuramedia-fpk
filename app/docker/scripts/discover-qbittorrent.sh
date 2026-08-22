#!/bin/bash
set -euo pipefail
: "${TRIM_APPDEST:?缺少 TRIM_APPDEST}"
: "${TRIM_PKGVAR:?缺少 TRIM_PKGVAR}"
PYTHON="${PYTHON:-/var/apps/python312/target/bin/python3}"
DATA_ROOT="${SAKURAMEDIA_DATA_ROOT:-$TRIM_PKGVAR/sakuramedia-data}"
"$PYTHON" "$TRIM_APPDEST/docker/scripts/discovery.py" \
  "$DATA_ROOT/integration-discovery" \
  "${SAKURAMEDIA_MEDIA_PARENT:-}" \
  "$DATA_ROOT/config/integration-secrets.json"
