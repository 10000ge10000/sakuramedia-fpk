#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$ROOT/dist"
BUILD="$ROOT/.build"
VERSION="$(awk -F= '$1=="version" {print $2}' "$ROOT/manifest")"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

# fnpack 1.2.3 Windows 版不会在 FPK 中保留 cmd/* 的 Unix 执行位；在 Windows
# Git Bash/MSYS 中自动转交 WSL 构建，确保产物可被 fnOS 接受。
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    command -v wsl.exe >/dev/null 2>&1 || {
      echo "Windows 构建需要 WSL，以保留 fnOS 生命周期脚本的执行权限。" >&2
      exit 1
    }
    WINDOWS_ROOT="$(cygpath -m "$ROOT")"
    # Git Bash 调 wsl.exe 时反斜杠会被当作转义吃掉，统一用正斜杠形式传给 wslpath。
    WSL_ROOT="$(wsl.exe wslpath -a "$WINDOWS_ROOT" | tr -d '\r')"
    exec wsl.exe bash -lc "cd $(printf '%q' "$WSL_ROOT") && ./build.sh"
    ;;
esac

"$ROOT/verify.sh"
mkdir -p "$DIST" "$BUILD"

resolve_fnpack() {
  if [[ -n "${FNPACK_BIN:-}" ]]; then printf '%s\n' "$FNPACK_BIN"; return; fi
  if command -v fnpack >/dev/null 2>&1; then command -v fnpack; return; fi
  local os arch url sha target
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os/$arch" in
    MINGW*/*|MSYS*/*|CYGWIN*/*)
      url="https://static2.fnnas.com/fnpack/fnpack-1.2.3-windows-amd64"
      sha="d7af4bd716b009c58f5bcd931615f39db121e7d4b75dc759e575c4fb2879b6ee"
      target="$BUILD/fnpack.exe"
      ;;
    Linux/x86_64|Linux/amd64)
      url="https://static2.fnnas.com/fnpack/fnpack-1.2.3-linux-amd64"
      sha="54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93"
      target="$BUILD/fnpack"
      ;;
    *) echo "当前平台无法自动下载 fnpack，请设置 FNPACK_BIN。" >&2; exit 1 ;;
  esac
  if [[ ! -f "$target" ]] || [[ "$(sha256sum "$target" | awk '{print $1}')" != "$sha" ]]; then
    curl -fL --retry 3 --connect-timeout 20 "$url" -o "$target.download"
    [[ "$(sha256sum "$target.download" | awk '{print $1}')" == "$sha" ]] || { echo "fnpack SHA-256 校验失败" >&2; exit 1; }
    mv "$target.download" "$target"
    chmod 755 "$target"
  fi
  printf '%s\n' "$target"
}

FNPACK="$(resolve_fnpack)"
marker="$BUILD/build-start"
touch "$marker"
"$FNPACK" build --directory "$ROOT"

mapfile -t products < <(find "$ROOT" "$(dirname "$ROOT")" -maxdepth 1 -type f -name '*.fpk' -newer "$marker" -print)
if [[ ${#products[@]} -ne 1 ]]; then
  echo "无法唯一定位 fnpack 产物，发现 ${#products[@]} 个。" >&2
  printf '%s\n' "${products[@]:-}" >&2
  exit 1
fi
output="$DIST/sakuramedia-$VERSION.fpk"
cp "${products[0]}" "$output"
"$PYTHON_BIN" "$ROOT/scripts/inspect-fpk.py" "$output"
(cd "$DIST" && sha256sum "$(basename "$output")") > "$output.sha256"
printf '构建完成：%s\n' "$output"
