#!/usr/bin/env python3
"""FPK 生命周期脚本共用的安全工具。仅使用 Python 标准库。"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable


class FpkError(RuntimeError):
    pass


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any, mode: int = 0o600) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", mode)


def run(args: Iterable[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise FpkError(f"命令执行失败：{args!r}：{detail[:500]}")
    return result


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_absolute_safe_path(raw: str, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise FpkError(f"{label}必须是绝对路径：{raw}")
    resolved = path.resolve(strict=False)
    if resolved == Path(resolved.anchor) or str(resolved) in {"/vol1", "/vol2", "/vol3"}:
        raise FpkError(f"{label}不能是根目录或存储卷根目录：{resolved}")
    return resolved


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]}"


def random_password(length: int = 48) -> str:
    while True:
        value = secrets.token_urlsafe(length)
        if all(ch not in value for ch in "\r\n\0"):
            return value


def compose_env_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$")
    return f'"{escaped}"'


def write_user_log(message: str) -> None:
    target = os.environ.get("TRIM_TEMP_LOGFILE")
    if target:
        Path(target).write_text(message.rstrip() + "\n", encoding="utf-8")
    else:
        print(message)

