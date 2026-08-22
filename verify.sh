#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

echo "[1/7] 检查必需文件"
required=(manifest config/privilege config/resource ICON.PNG ICON_256.PNG app/ui/config app/docker/docker-compose.yaml cmd/main wizard/install)
for path in "${required[@]}"; do
  [[ -e "$path" ]] || { echo "缺少必需文件：$path" >&2; exit 1; }
done

echo "[2/7] 检查 Shell 语法"
while IFS= read -r -d '' path; do bash -n "$path"; done < <(find cmd scripts app/docker/scripts -type f -name '*.sh' -print0)
bash -n cmd/main cmd/install_init cmd/install_callback cmd/config_init cmd/config_callback cmd/upgrade_init cmd/upgrade_callback cmd/uninstall_init cmd/uninstall_callback
if command -v shellcheck >/dev/null 2>&1; then
  mapfile -d '' shell_files < <(find cmd scripts app/docker/scripts -type f \( -name '*.sh' -o -path 'cmd/main' -o -path 'cmd/*_init' -o -path 'cmd/*_callback' \) -print0)
  # 生命周期入口必须按脚本实际安装位置动态加载 runtime.sh，SC1091 在此场景无可解析的静态路径。
  shellcheck -e SC1091 "${shell_files[@]}"
else
  echo "ShellCheck 未安装，已跳过。"
fi

echo "[3/7] 检查 JSON 和 Python 语法"
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
for root in (Path('config'), Path('wizard'), Path('app/ui')):
    for path in root.iterdir():
        if path.is_file():
            json.loads(path.read_text(encoding='utf-8'))
PY
"$PYTHON_BIN" - <<'PY'
from pathlib import Path
for root in (Path('app/docker/scripts'), Path('tests'), Path('scripts')):
    for path in root.rglob('*.py'):
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
PY

echo "[4/7] 运行自动化单元测试"
"$PYTHON_BIN" -m unittest discover -s tests -v

echo "[5/7] 校验轻量/完整 Compose"
docker compose --env-file tests/compose-light.env -f app/docker/docker-compose.yaml config --quiet
docker compose --env-file tests/compose-full.env -f app/docker/docker-compose.yaml --profile full config --quiet

echo "[6/7] 检查敏感信息和固定弱密码"
if grep -RInE '(ghp_[A-Za-z0-9]{20,}|POSTGRES_PASSWORD:[[:space:]]*sakuramedia|BEGIN (RSA |OPENSSH )?PRIVATE KEY)' . \
  --exclude=verify.sh --exclude-dir=dist --exclude-dir=.build --exclude-dir=__pycache__; then
  echo "发现疑似敏感信息或固定弱密码。" >&2
  exit 1
fi

echo "[7/7] 检查版本与模型校验值"
grep -q '^version=1.1.0$' manifest
grep -Eq 'x86\|x86_64\|amd64' cmd/install_init
grep -q 'v0.4.21@sha256:3977291e9531' app/docker/docker-compose.yaml
grep -q 'v0.4.13@sha256:22bd7b3a831e' app/docker/docker-compose.yaml
grep -q '8b9b2f12e2c656d9bbe0bf695cd4716d29e10a86a30bb95568c9890a23e9e46c' app/docker/scripts/lifecycle.py
grep -q 'DEFAULT_ACCOUNT_USERNAME = "yiwan"' app/docker/scripts/lifecycle.py
grep -q 'DEFAULT_ACCOUNT_PASSWORD = "yiwan123"' app/docker/scripts/lifecycle.py
if grep -q 'wizard_sm_password' wizard/install; then
  echo "首次安装向导不应再要求填写 SakuraMedia 密码。" >&2
  exit 1
fi

echo "全部静态检查与单元测试通过。"
