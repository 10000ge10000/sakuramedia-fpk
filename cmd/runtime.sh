#!/bin/bash
set -euo pipefail

runtime_python() {
  local candidate
  for candidate in /var/apps/python312/target/bin/python3 /var/apps/python312/target/bin/python python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

runtime_script() {
  local name="$1"
  local candidate package_root
  package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  for candidate in \
    "${TRIM_APPDEST:-/var/apps/sakuramedia/target}/docker/scripts/$name" \
    "$package_root/app/docker/scripts/$name" \
    "${TRIM_TEMP_TPKFILE:-}/app/docker/scripts/$name" \
    "${TRIM_PKGINST_TEMP_DIR:-}/app/docker/scripts/$name"; do
    if [ -n "$candidate" ] && [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

write_user_error() {
  local message="$1"
  if [ -n "${TRIM_TEMP_LOGFILE:-}" ]; then
    printf '%s\n' "$message" > "$TRIM_TEMP_LOGFILE"
  else
    printf '%s\n' "$message" >&2
  fi
}

run_lifecycle() {
  local action="$1"
  local python script
  python="$(runtime_python)" || {
    write_user_error "未找到 fnOS python312 运行时，请确认应用依赖已正确安装。"
    return 1
  }
  script="$(runtime_script lifecycle.py)" || {
    write_user_error "SakuraMedia 生命周期脚本缺失，请重新安装 FPK。"
    return 1
  }
  "$python" "$script" "$action"
}
