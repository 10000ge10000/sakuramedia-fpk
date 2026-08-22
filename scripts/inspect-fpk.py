#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import stat
import sys
import tarfile
from pathlib import Path

REQUIRED = {
    "manifest",
    "config/privilege",
    "config/resource",
    "ICON.PNG",
    "ICON_256.PNG",
    "cmd/main",
    "wizard/install",
}
APP_REQUIRED = {
    "docker/docker-compose.yaml",
    "ui/config",
    "ui/images/icon_64.png",
    "ui/images/icon_256.png",
}


def main(path: Path) -> int:
    try:
        archive = tarfile.open(path, "r:*")
    except tarfile.TarError as exc:
        print(f"无法按 tar 格式检查 FPK：{exc}", file=sys.stderr)
        return 1
    members = {item.name.lstrip("./"): item for item in archive.getmembers()}
    missing = sorted(REQUIRED - set(members))
    if missing:
        print("FPK 缺少文件：" + ", ".join(missing), file=sys.stderr)
        return 1
    app_bundle = members.get("app.tgz")
    if app_bundle is None:
        print("FPK 缺少 app.tgz", file=sys.stderr)
        return 1
    app_file = archive.extractfile(app_bundle)
    if app_file is None:
        print("无法读取 app.tgz", file=sys.stderr)
        return 1
    nested = tarfile.open(fileobj=io.BytesIO(app_file.read()), mode="r:gz")
    app_members = {item.name.lstrip("./"): item for item in nested.getmembers()}
    missing_app = sorted(APP_REQUIRED - set(app_members))
    if missing_app:
        print("app.tgz 缺少文件：" + ", ".join(missing_app), file=sys.stderr)
        return 1
    non_exec = [name for name, item in members.items() if name.startswith("cmd/") and item.isfile() and not (item.mode & stat.S_IXUSR)]
    if non_exec:
        print("生命周期脚本缺少执行权限：" + ", ".join(non_exec), file=sys.stderr)
        return 1
    print(json.dumps({"fpk": str(path), "members": len(members), "app_members": len(app_members), "required": "ok", "cmd_executable": "ok"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))