#!/usr/bin/env python3
"""fnOS FPK 生命周期实现。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from discovery import perform_discovery
from runtime_utils import (
    FpkError,
    atomic_write,
    compose_env_quote,
    env_bool,
    env_value,
    load_json,
    random_password,
    require_absolute_safe_path,
    run,
    save_json,
    write_user_log,
)

MODEL_URL = "https://github.com/tinypinglite/sakuramediabe/releases/download/model/model_vit_768.onnx"
MODEL_SHA256 = "8b9b2f12e2c656d9bbe0bf695cd4716d29e10a86a30bb95568c9890a23e9e46c"
MARKER_NAME = ".sakuramedia-fnos-fpk"
DEFAULT_ACCOUNT_USERNAME = "yiwan"
DEFAULT_ACCOUNT_PASSWORD = "yiwan123"


def app_dest() -> Path:
    return Path(os.environ.get("TRIM_APPDEST", "/var/apps/sakuramedia/target"))


def pkg_var() -> Path:
    return Path(os.environ.get("TRIM_PKGVAR", "/var/apps/sakuramedia/var"))


def load_current_config() -> dict:
    candidates = [
        pkg_var() / "sakuramedia-data" / "config" / "fpk-config.json",
        Path(os.environ.get("SAKURAMEDIA_DATA_ROOT", "/nonexistent")) / "config" / "fpk-config.json",
    ]
    for candidate in candidates:
        data = load_json(candidate, None)
        if data:
            return data
    return {}


def resolve_data_root(existing: dict | None = None) -> Path:
    existing = existing or {}
    # 首次安装只显示一个可选的自定义路径：留空即使用 fnOS 托管目录。
    # 兼容旧版 wizard_data_mode，避免升级时丢失原有数据位置。
    mode_from_wizard = env_value("wizard_data_mode", "")
    custom_from_wizard = env_value("wizard_data_dir", "")
    existing_mode = str(existing.get("data_mode") or "")
    existing_root = str(existing.get("data_root") or "")
    if mode_from_wizard:
        data_mode = mode_from_wizard
    elif custom_from_wizard:
        data_mode = "custom"
    else:
        data_mode = existing_mode or "managed"
    custom = custom_from_wizard or existing_root
    if data_mode == "managed":
        return require_absolute_safe_path(str(pkg_var() / "sakuramedia-data"), "数据目录")
    if data_mode != "custom" or not custom:
        raise FpkError("自定义数据目录模式必须填写绝对路径。")
    return require_absolute_safe_path(custom, "数据目录")


def build_config(existing: dict | None = None) -> tuple[dict, dict]:
    existing = existing or {}
    data_root = resolve_data_root(existing)
    media_parent_raw = env_value("wizard_media_parent", str(existing.get("media_parent") or ""))
    media_parent = require_absolute_safe_path(media_parent_raw, "媒体父目录")
    if not media_parent.is_dir():
        raise FpkError(f"媒体父目录不存在：{media_parent}")
    deploy_mode = env_value(
        "wizard_deploy_mode",
        env_value("COMPOSE_PROFILES", str(existing.get("deploy_mode") or "")),
    )
    if deploy_mode not in {"light", "full"}:
        raise FpkError("部署模式必须是 light 或 full。")
    api_port = int(env_value("wizard_api_port", str(existing.get("api_port") or 38000)))
    web_port = int(env_value("wizard_web_port", str(existing.get("web_port") or 38080)))
    if not all(1024 <= item <= 65535 for item in (api_port, web_port)) or api_port == web_port:
        raise FpkError("API/Web 端口必须不同，且位于 1024-65535。")
    config = {
        "schema_version": 1,
        "deploy_mode": deploy_mode,
        "data_mode": "custom" if data_root != (pkg_var() / "sakuramedia-data").resolve(strict=False) else "managed",
        "data_root": str(data_root),
        "media_parent": str(media_parent),
        "api_port": api_port,
        "web_port": web_port,
        "puid": int(env_value("wizard_puid", "") or str(existing.get("puid") or 1000)),
        "pgid": int(env_value("wizard_pgid", "") or str(existing.get("pgid") or 1000)),
        "timezone": env_value("wizard_timezone", "") or str(existing.get("timezone") or "Asia/Shanghai"),
        "discover_qb": env_bool("wizard_discover_qb", bool(existing.get("discover_qb", True))),
        "discover_jackett": env_bool("wizard_discover_jackett", bool(existing.get("discover_jackett", True))),
        "import_indexers": env_bool("wizard_import_indexers", bool(existing.get("import_indexers", True))),
        "config_action": env_value("wizard_config_action", "keep"),
        "qb_candidate_id": env_value("wizard_qb_candidate_id", str(existing.get("qb_candidate_id") or "")),
        "jackett_candidate_id": env_value("wizard_jackett_candidate_id", str(existing.get("jackett_candidate_id") or "")),
        "qb_manual": {
            "base_url": env_value("wizard_qb_url", str((existing.get("qb_manual") or {}).get("base_url") or "")),
            "username": env_value("wizard_qb_username", str((existing.get("qb_manual") or {}).get("username") or "")),
            "client_save_path": env_value("wizard_qb_save_path", str((existing.get("qb_manual") or {}).get("client_save_path") or "")),
            "local_root_path": env_value("wizard_qb_local_path", str((existing.get("qb_manual") or {}).get("local_root_path") or "")),
        },
        "jackett_manual": {
            "base_url": env_value("wizard_jackett_url", str((existing.get("jackett_manual") or {}).get("base_url") or "")),
        },
    }
    secrets_path = data_root / "config" / "fpk-secrets.json"
    secrets = load_json(secrets_path, {}) or {}
    database_password_file = data_root / "config" / "postgres-password"
    if database_password_file.is_file():
        database_password = database_password_file.read_text(encoding="utf-8").strip()
        if len(database_password) < 32:
            raise FpkError("PostgreSQL 密码文件内容无效，拒绝继续配置。")
        secrets["database_password"] = database_password
    else:
        secrets.setdefault("database_password", random_password())
    account = secrets.setdefault("sakuramedia_account", {})
    # 固定目标账号。已有安装先保存旧凭据到 600 秘密文件，bootstrap 只用它完成一次迁移。
    old_username = str(account.get("username") or "")
    old_password = str(account.get("password") or "")
    if old_username and old_password and (old_username, old_password) != (
        DEFAULT_ACCOUNT_USERNAME,
        DEFAULT_ACCOUNT_PASSWORD,
    ):
        secrets["sakuramedia_legacy_account"] = {
            "username": old_username,
            "password": old_password,
        }
    account.update({"username": DEFAULT_ACCOUNT_USERNAME, "password": DEFAULT_ACCOUNT_PASSWORD})
    integrations = secrets.setdefault("integrations", {})
    integrations.setdefault("manual-qbittorrent", {})
    integrations["manual-qbittorrent"].update(
        {
            "username": config["qb_manual"]["username"],
            "password": env_value("wizard_qb_password", str(integrations["manual-qbittorrent"].get("password") or "")),
        }
    )
    integrations.setdefault("manual-jackett", {})
    integrations["manual-jackett"]["api_key"] = env_value(
        "wizard_jackett_api_key", str(integrations["manual-jackett"].get("api_key") or "")
    )
    return config, secrets


def prepare_directories(config: dict) -> None:
    data_root = Path(config["data_root"])
    for name in ("postgres", "image-search-index", "joytag", "logs", "config", "integration-discovery"):
        (data_root / name).mkdir(parents=True, exist_ok=True)
    marker = data_root / MARKER_NAME
    if not marker.exists():
        atomic_write(marker, json.dumps({"appname": "sakuramedia", "created_at": int(time.time())}) + "\n", 0o600)
    media_parent = Path(config["media_parent"])
    (media_parent / "downloads").mkdir(exist_ok=True)
    (media_parent / "sakuramedia").mkdir(exist_ok=True)
    devices = {path.name: path.stat().st_dev for path in (media_parent / "downloads", media_parent / "sakuramedia")}
    av = media_parent / "av"
    if av.exists():
        devices["av"] = av.stat().st_dev
    if len(set(devices.values())) > 1:
        write_user_log("警告：媒体目录不在同一文件系统，硬链接不可用，入库可能退化为复制。")


def ensure_model(config: dict) -> None:
    if config["deploy_mode"] != "full":
        return
    target = Path(config["data_root"]) / "joytag" / "model_vit_768.onnx"
    if target.exists() and _sha256(target) == MODEL_SHA256:
        return
    tmp = target.with_suffix(".onnx.download")
    tmp.unlink(missing_ok=True)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=120) as response, tmp.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        if _sha256(tmp) != MODEL_SHA256:
            raise FpkError("JoyTag 模型 SHA-256 校验失败。")
        os.replace(tmp, target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_backend_config(config: dict, secrets: dict) -> None:
    path = Path(config["data_root"]) / "config" / "config.toml"
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return
    # 首次 Compose 启动时由 PostgreSQL 入口脚本原子生成同源密码与 config.toml。
    # install_callback 可能早于容器启动，不能在密码文件出现前另造一套数据库凭据。
    if not (Path(config["data_root"]) / "config" / "postgres-password").is_file():
        return
    db_password = urllib.parse.quote(str(secrets["database_password"]), safe="")
    account = secrets["sakuramedia_account"]
    content = (
        "[database]\n"
        f'url = "postgresql://sakuramedia:{db_password}@postgres:5432/sakuramedia"\n\n'
        "[auth]\n"
        f'username = {json.dumps(account["username"], ensure_ascii=False)}\n'
        f'password = {json.dumps(account["password"], ensure_ascii=False)}\n'
    )
    atomic_write(path, content, 0o600)


def write_compose_env(config: dict, secrets: dict) -> None:
    values = {
        "wizard_data_dir": config["data_root"],
        "wizard_media_parent": config["media_parent"],
        "wizard_api_port": str(config["api_port"]),
        "wizard_web_port": str(config["web_port"]),
        "wizard_puid": str(config["puid"]),
        "wizard_pgid": str(config["pgid"]),
        "wizard_timezone": config["timezone"],
        "COMPOSE_PROFILES": "full" if config["deploy_mode"] == "full" else "",
    }
    content = "".join(f"{key}={compose_env_quote(str(value))}\n" for key, value in values.items())
    atomic_write(app_dest() / "docker" / ".env", content, 0o600)


def save_configuration(config: dict, secrets: dict) -> None:
    data_root = Path(config["data_root"])
    save_json(data_root / "config" / "fpk-config.json", config, 0o600)
    save_json(data_root / "config" / "fpk-secrets.json", secrets, 0o600)


def discover(config: dict, secrets: dict) -> dict:
    data_root = Path(config["data_root"])
    integration_secrets_path = data_root / "config" / "integration-secrets.json"
    report = perform_discovery(data_root / "integration-discovery", config["media_parent"], integration_secrets_path)
    discovered = load_json(integration_secrets_path, {}) or {}
    secrets.setdefault("integrations", {}).update(discovered)
    save_json(data_root / "config" / "fpk-secrets.json", secrets, 0o600)
    return report


def apply_configuration() -> dict:
    existing = load_current_config()
    config, secrets = build_config(existing)
    prepare_directories(config)
    stat = os.statvfs(config["data_root"])
    free_bytes = stat.f_bavail * stat.f_frsize
    minimum = 5 * 1024**3 if config["deploy_mode"] == "full" else 1 * 1024**3
    if free_bytes < minimum:
        raise FpkError(f"数据目录可用空间不足，当前模式至少需要 {minimum // 1024**3} GiB。")
    ensure_model(config)
    write_backend_config(config, secrets)
    save_configuration(config, secrets)
    write_compose_env(config, secrets)
    if config["discover_qb"] or config["discover_jackett"]:
        discover(config, secrets)
    return config


def schedule_bootstrap(config: dict) -> None:
    tmp = Path(os.environ.get("TRIM_PKGTMP", str(pkg_var() / "tmp")))
    tmp.mkdir(parents=True, exist_ok=True)
    pid_file = tmp / "bootstrap.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), 0)
            return
        except (ValueError, ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)
    python = Path("/var/apps/python312/target/bin/python3")
    if not python.exists():
        python = Path(sys.executable)
    log_path = Path(config["data_root"]) / "logs" / "bootstrap.log"
    handle = log_path.open("ab", buffering=0)
    process = subprocess.Popen(
        [str(python), str(app_dest() / "docker" / "scripts" / "bootstrap_sakuramedia.py"), config["data_root"], "600"],
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    atomic_write(pid_file, f"{process.pid}\n", 0o600)


def stop_bootstrap() -> None:
    pid_file = Path(os.environ.get("TRIM_PKGTMP", str(pkg_var() / "tmp"))) / "bootstrap.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    pid_file.unlink(missing_ok=True)


def status() -> int:
    config = load_current_config()
    if not config:
        write_user_log("SakuraMedia 尚未完成配置。")
        return 3
    required = ["sakuramedia-postgres", "sakuramedia", "sakuramedia-web"]
    if config.get("deploy_mode") == "full":
        required.extend(["joytag-infer", "qdrant"])
    states = {}
    for name in required:
        result = run(["docker", "inspect", "-f", "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}", name], check=False)
        states[name] = result.stdout.strip() if result.returncode == 0 else "missing"
    if all(value == "missing" or value.startswith("exited") for value in states.values()):
        return 3
    problems = [f"{name}={value}" for name, value in states.items() if not value.startswith("running") or value.endswith("unhealthy")]
    if not problems:
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{config['api_port']}/auth/tokens",
                data=b'{"username":"__fnos_status_probe__","password":"invalid"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code not in {401, 422}:
                problems.append(f"API 返回 HTTP {exc.code}")
        except Exception as exc:
            problems.append(f"API 无法访问：{type(exc).__name__}")
    if problems:
        write_user_log("SakuraMedia 服务异常：" + "；".join(problems))
        return 1
    return 0


def backup_upgrade() -> None:
    config = load_current_config()
    if not config:
        return
    data_root = Path(config["data_root"])
    backup_dir = data_root / "config" / "backups" / f"upgrade-{int(time.time())}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in [data_root / "config" / "fpk-config.json", data_root / "config" / "fpk-secrets.json", app_dest() / "docker" / ".env"]:
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
    discovery_dir = data_root / "integration-discovery"
    if discovery_dir.exists():
        shutil.copytree(discovery_dir, backup_dir / "integration-discovery", dirs_exist_ok=True)
    state = run(["docker", "inspect", "-f", "{{.State.Status}}", "sakuramedia-postgres"], check=False).stdout.strip()
    if state == "running":
        dump_path = backup_dir / "postgres.sql"
        with dump_path.open("wb") as handle:
            result = subprocess.run(["docker", "exec", "sakuramedia-postgres", "pg_dump", "-U", "sakuramedia", "sakuramedia"], stdout=handle, stderr=subprocess.PIPE)
        if result.returncode:
            dump_path.unlink(missing_ok=True)
            raise FpkError("升级前 PostgreSQL 备份失败，已停止升级。")


def uninstall_callback() -> None:
    config = load_current_config()
    if not config:
        return
    root = Path(config["data_root"]).resolve(strict=False)
    marker = root / MARKER_NAME
    if not marker.is_file():
        raise FpkError("数据目录缺少 SakuraMedia marker，拒绝执行删除。")
    if env_bool("wizard_remove_runtime"):
        for name in ("image-search-index", "joytag", "logs"):
            shutil.rmtree(root / name, ignore_errors=False) if (root / name).exists() else None
    if env_bool("wizard_remove_postgres") and (root / "postgres").exists():
        shutil.rmtree(root / "postgres")
    if env_bool("wizard_remove_integrations"):
        if (root / "integration-discovery").exists():
            shutil.rmtree(root / "integration-discovery")
        for name in ("integration-secrets.json", "fpk-secrets.json", "bootstrap-state.json"):
            (root / "config" / name).unlink(missing_ok=True)


def main(action: str) -> int:
    try:
        if action in {"install", "config", "upgrade-callback"}:
            config = apply_configuration()
            schedule_bootstrap(config)
            return 0
        if action == "validate-config":
            build_config(load_current_config())
            return 0
        if action == "upgrade-init":
            backup_upgrade()
            return 0
        if action == "uninstall-init":
            stop_bootstrap()
            return 0
        if action == "uninstall-callback":
            uninstall_callback()
            return 0
        if action == "start":
            config = load_current_config()
            if config:
                schedule_bootstrap(config)
            return 0
        if action == "stop":
            stop_bootstrap()
            return 0
        if action == "status":
            return status()
        raise FpkError(f"未知生命周期动作：{action}")
    except Exception as exc:
        message = f"SakuraMedia {action} 失败：{exc}"
        write_user_log(message)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
