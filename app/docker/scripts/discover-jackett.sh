#!/bin/bash
set -euo pipefail
exec "$(dirname "$0")/discover-qbittorrent.sh" "$@"
