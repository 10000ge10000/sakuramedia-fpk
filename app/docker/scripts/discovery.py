#!/usr/bin/env python3
"""只读发现 Docker 中的 qBittorrent 与 Jackett 实例。"""

from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from runtime_utils import FpkError, load_json, mask_secret, run, save_json

Reader = Callable[[Path], str]
# 返回响应正文，失败返回 None；注入以便单元测试离线运行。
HttpFetch = Callable[[str], "str | None"]


def _default_http_get(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                return None
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _env_map(inspect: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in inspect.get("Config", {}).get("Env") or []:
        if "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


def _labels(inspect: dict[str, Any]) -> dict[str, str]:
    return inspect.get("Config", {}).get("Labels") or {}


def _mounts(inspect: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in inspect.get("Mounts") or [] if item.get("Source") and item.get("Destination")]


def _stable_id(kind: str, inspect: dict[str, Any]) -> str:
    raw = "|".join(
        [kind, str(inspect.get("Id", "")), str(inspect.get("Name", "")), str(inspect.get("Config", {}).get("Image", ""))]
    )
    return f"{kind[:2]}-{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _published_port(inspect: dict[str, Any], preferred: tuple[str, ...]) -> tuple[str, str] | None:
    ports = inspect.get("NetworkSettings", {}).get("Ports") or {}
    for container_port in preferred:
        bindings = ports.get(container_port) or []
        for binding in bindings:
            host_port = str(binding.get("HostPort", "")).strip()
            if host_port:
                return container_port.split("/", 1)[0], host_port
    for container_port, bindings in ports.items():
        for binding in bindings or []:
            host_port = str(binding.get("HostPort", "")).strip()
            if host_port:
                return container_port.split("/", 1)[0], host_port
    return None


def map_container_path(
    container_path: str,
    mounts: list[dict[str, Any]],
    media_parent: str | None,
) -> dict[str, Any]:
    normalized = str(PurePosixPath(container_path or "/"))
    matches: list[tuple[int, dict[str, Any]]] = []
    for mount in mounts:
        destination = str(PurePosixPath(str(mount["Destination"])))
        if normalized == destination or normalized.startswith(destination.rstrip("/") + "/"):
            matches.append((len(destination), mount))
    if not matches:
        return {"status": "unmapped", "client_path": normalized}
    mount = max(matches, key=lambda item: item[0])[1]
    destination = str(PurePosixPath(str(mount["Destination"])))
    suffix = normalized[len(destination) :].lstrip("/")
    host_path = Path(str(mount["Source"])) / suffix
    result: dict[str, Any] = {
        "status": "host-mapped",
        "client_path": normalized,
        "host_path": str(host_path),
        "mount_destination": destination,
        "mount_read_only": not bool(mount.get("RW", True)),
    }
    if media_parent:
        parent = Path(media_parent).resolve(strict=False)
        resolved = host_path.resolve(strict=False)
        try:
            relative = resolved.relative_to(parent)
        except ValueError:
            result["status"] = "outside-media-parent"
        else:
            result["status"] = "mapped"
            result["local_path"] = str(PurePosixPath("/mnt/media1") / PurePosixPath(relative.as_posix()))
    return result


def _find_config_mount(mounts: list[dict[str, Any]]) -> Path | None:
    candidates = sorted(
        (item for item in mounts if str(item.get("Destination", "")).rstrip("/") in {"/config", "/data"}),
        key=lambda item: 0 if str(item.get("Destination", "")).rstrip("/") == "/config" else 1,
    )
    return Path(str(candidates[0]["Source"])) if candidates else None


def _read_qb_config(config_root: Path | None, reader: Reader) -> tuple[dict[str, str], Path | None]:
    if not config_root:
        return {}, None
    patterns = ["qBittorrent/config/qBittorrent.conf", "config/qBittorrent.conf", "qBittorrent.conf"]
    path = next((config_root / item for item in patterns if (config_root / item).is_file()), None)
    if not path:
        return {}, None
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(reader(path))
    flat: dict[str, str] = {}
    for section in parser.sections():
        for key, value in parser.items(section):
            flat[f"{section}\\{key}"] = value
    return flat, path


def _qb_candidate(inspect: dict[str, Any], media_parent: str | None, reader: Reader) -> tuple[dict[str, Any], dict[str, str]] | None:
    env = _env_map(inspect)
    labels = _labels(inspect)
    name = str(inspect.get("Name", "")).lstrip("/")
    image = str(inspect.get("Config", {}).get("Image", ""))
    signal = " ".join([name, image, json.dumps(labels), " ".join(env)]).lower()
    mounts = _mounts(inspect)
    config_values, config_path = _read_qb_config(_find_config_mount(mounts), reader)
    score = (5 if "qbittorrent" in signal or "qbittorrent-nox" in signal else 0) + (2 if config_path else 0) + (1 if "WEBUI_PORT" in env else 0)
    if score < 3:
        return None
    port = _published_port(inspect, ("8080/tcp", f"{env.get('WEBUI_PORT', '')}/tcp"))
    save_path = env.get("QBITTORRENT_DOWNLOAD_DIR") or config_values.get("Preferences\\Downloads\\SavePath") or config_values.get("Downloads\\SavePath") or ""
    username = env.get("QBITTORRENT_USERNAME") or env.get("WEBUI_USERNAME") or config_values.get("Preferences\\WebUI\\Username") or config_values.get("WebUI\\Username") or ""
    password = env.get("QBITTORRENT_PASSWORD") or env.get("WEBUI_PASSWORD") or ""
    hash_present = any("Password" in key and bool(value) for key, value in config_values.items()) and not password
    candidate_id = _stable_id("qbittorrent", inspect)
    networks = sorted((inspect.get("NetworkSettings", {}).get("Networks") or {}).keys())
    mapping = map_container_path(save_path, mounts, media_parent) if save_path else {"status": "unknown"}
    public = {
        "candidate_id": candidate_id,
        "container_id": str(inspect.get("Id", ""))[:12],
        "container_name": name,
        "image": image,
        "score": score,
        "status": inspect.get("State", {}).get("Status"),
        "health": inspect.get("State", {}).get("Health", {}).get("Status"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "networks": networks,
        "published_port": port[1] if port else None,
        "container_port": port[0] if port else env.get("WEBUI_PORT") or "8080",
        "base_url": f"http://host.docker.internal:{port[1]}" if port else None,
        "username": username,
        "password_state": "plaintext-available" if password else ("hash-only" if hash_present else "missing"),
        "client_save_path": save_path,
        "path_mapping": mapping,
        "mounts": [{"source": m["Source"], "destination": m["Destination"], "rw": bool(m.get("RW", True))} for m in mounts],
        "secret_ref": candidate_id,
    }
    secret = {"username": username, "password": password}
    return public, secret


def _jackett_indexers(root: Path, base_url: str | None, reader: Reader) -> list[dict[str, Any]]:
    indexer_dir = root / "Jackett" / "Indexers"
    if not indexer_dir.is_dir():
        indexer_dir = root / "Indexers"
    result: list[dict[str, Any]] = []
    for path in sorted(indexer_dir.glob("*.json")):
        try:
            payload = json.loads(reader(path))
        except (OSError, json.JSONDecodeError):
            continue
        indexer_id = path.stem
        if isinstance(payload, list):
            fields = {
                str(item.get("id") or item.get("name") or ""): item.get("value")
                for item in payload
                if isinstance(item, dict)
            }
        elif isinstance(payload, dict):
            fields = payload
        else:
            continue
        name = str(fields.get("name") or fields.get("Name") or fields.get("title") or indexer_id)
        # 现实中的列表型配置 type 是控件类型，几乎必然得不出隐私类型；
        # 这里只作为 API 不可用时的兜底提示，权威来源是 torznab t=indexers。
        raw_type = str(fields.get("type") or fields.get("Type") or "").lower()
        kind = "pt" if "private" in raw_type else ("bt" if "public" in raw_type else None)
        result.append(
            {
                "id": indexer_id,
                "name": name,
                "kind": kind,
                "needs_kind_confirmation": kind is None,
                "torznab_url": f"{base_url}/api/v2.0/indexers/{indexer_id}/results/torznab/api" if base_url else None,
            }
        )
    return result


# Jackett 站点类型到 SakuraMedia kind 的映射；semi-private 需要账号，按 PT 处理。
JACKETT_KIND_MAP = {"public": "bt", "private": "pt", "semi-private": "pt"}


def _torznab_indexer_catalog(
    host_base_url: str | None,
    api_key: str,
    http_get: HttpFetch,
) -> dict[str, dict[str, Any]] | None:
    """通过 torznab t=indexers 接口获取已配置 Indexer 的权威名称与类型。

    该接口使用与 Torznab 相同的 apikey 认证，不依赖 Jackett 管理端会话；
    URL 中的 apikey 不得出现在任何报告里。
    """
    if not host_base_url or not api_key:
        return None
    url = (
        f"{host_base_url}/api/v2.0/indexers/all/results/torznab/api"
        f"?t=indexers&apikey={urllib.parse.quote(api_key, safe='')}"
    )
    body = http_get(url)
    if not body:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    catalog: dict[str, dict[str, Any]] = {}
    for node in root.findall("indexer"):
        indexer_id = str(node.get("id") or "").strip()
        if not indexer_id:
            continue
        raw_type = str(node.findtext("type") or "").strip().lower()
        catalog[indexer_id] = {
            "name": str(node.findtext("title") or "").strip() or indexer_id,
            "type": raw_type,
            "configured": str(node.get("configured") or "").strip().lower() == "true",
            "kind": JACKETT_KIND_MAP.get(raw_type),
        }
    return catalog or None


def _indexers_from_catalog(catalog: dict[str, dict[str, Any]], base_url: str | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for indexer_id, info in sorted(catalog.items()):
        if not info.get("configured"):
            continue
        kind = info.get("kind")
        result.append(
            {
                "id": indexer_id,
                "name": info["name"],
                "kind": kind,
                "needs_kind_confirmation": kind is None,
                "torznab_url": f"{base_url}/api/v2.0/indexers/{indexer_id}/results/torznab/api" if base_url else None,
            }
        )
    return result


def _jackett_candidate(
    inspect: dict[str, Any],
    reader: Reader,
    http_fetch: HttpFetch | None = None,
) -> tuple[dict[str, Any], dict[str, str]] | None:
    env = _env_map(inspect)
    labels = _labels(inspect)
    name = str(inspect.get("Name", "")).lstrip("/")
    image = str(inspect.get("Config", {}).get("Image", ""))
    signal = " ".join([name, image, json.dumps(labels), " ".join(env)]).lower()
    mounts = _mounts(inspect)
    root = _find_config_mount(mounts)
    server_config: dict[str, Any] = {}
    config_path: Path | None = None
    if root:
        options = [root / "Jackett" / "ServerConfig.json", root / "ServerConfig.json"]
        config_path = next((path for path in options if path.is_file()), None)
        if config_path:
            try:
                server_config = json.loads(reader(config_path))
            except json.JSONDecodeError:
                server_config = {}
    score = (5 if "jackett" in signal else 0) + (2 if config_path else 0)
    if score < 3:
        return None
    port = _published_port(inspect, ("9117/tcp",))
    base_url = f"http://host.docker.internal:{port[1]}" if port else None
    api_key = str(env.get("JACKETT_API_KEY") or server_config.get("APIKey") or "")
    candidate_id = _stable_id("jackett", inspect)
    # 发现进程运行在宿主机上，用 127.0.0.1 直连本地端口获取权威 Indexer 目录。
    host_base_url = f"http://127.0.0.1:{port[1]}" if port else None
    catalog = _torznab_indexer_catalog(host_base_url, api_key, http_fetch) if http_fetch else None
    if catalog:
        indexers = _indexers_from_catalog(catalog, base_url)
        # API 目录缺失但配置文件存在的 Indexer 保留为兜底候选。
        catalog_ids = {item["id"] for item in indexers}
        for item in _jackett_indexers(root, base_url, reader) if root else []:
            if item["id"] not in catalog_ids:
                indexers.append(item)
        indexer_source = "torznab-api"
    else:
        indexers = _jackett_indexers(root, base_url, reader) if root else []
        indexer_source = "config-files"
    public = {
        "candidate_id": candidate_id,
        "container_id": str(inspect.get("Id", ""))[:12],
        "container_name": name,
        "image": image,
        "score": score,
        "status": inspect.get("State", {}).get("Status"),
        "health": inspect.get("State", {}).get("Health", {}).get("Status"),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
        "networks": sorted((inspect.get("NetworkSettings", {}).get("Networks") or {}).keys()),
        "published_port": port[1] if port else None,
        "container_port": port[0] if port else "9117",
        "base_url": base_url,
        "api_key_state": "available" if api_key else "missing",
        "api_key_masked": mask_secret(api_key),
        "config_dir": str(root) if root else None,
        "indexer_source": indexer_source,
        "indexers": indexers,
        "secret_ref": candidate_id,
    }
    return public, {"api_key": api_key}


def discover_from_inspects(
    inspects: list[dict[str, Any]],
    *,
    media_parent: str | None = None,
    reader: Reader | None = None,
    http_fetch: HttpFetch | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, str]]]:
    reader = reader or (lambda path: path.read_text(encoding="utf-8", errors="replace"))
    qb: list[dict[str, Any]] = []
    jackett: list[dict[str, Any]] = []
    secrets: dict[str, dict[str, str]] = {}
    for inspect in inspects:
        q = _qb_candidate(inspect, media_parent, reader)
        if q:
            public, secret = q
            qb.append(public)
            secrets[public["candidate_id"]] = secret
        j = _jackett_candidate(inspect, reader, http_fetch)
        if j:
            public, secret = j
            jackett.append(public)
            secrets[public["candidate_id"]] = secret
    return qb, jackett, secrets


def inspect_docker() -> list[dict[str, Any]]:
    ids = run(["docker", "ps", "-aq"]).stdout.split()
    if not ids:
        return []
    payload = run(["docker", "inspect", *ids], timeout=120).stdout
    return json.loads(payload)


def perform_discovery(output_dir: Path, media_parent: str | None, secrets_path: Path) -> dict[str, Any]:
    qb, jackett, discovered_secrets = discover_from_inspects(
        inspect_docker(), media_parent=media_parent, http_fetch=_default_http_get
    )
    existing_secrets = load_json(secrets_path, {}) or {}
    for ref, values in discovered_secrets.items():
        old = existing_secrets.get(ref, {})
        existing_secrets[ref] = {key: value or old.get(key, "") for key, value in values.items()}
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(output_dir / "qbittorrent-candidates.json", qb, 0o600)
    save_json(output_dir / "jackett-candidates.json", jackett, 0o600)
    save_json(secrets_path, existing_secrets, 0o600)
    report = {
        "qbittorrent_count": len(qb),
        "jackett_count": len(jackett),
        "qbittorrent_requires_password": [item["candidate_id"] for item in qb if item["password_state"] != "plaintext-available"],
        "jackett_requires_api_key": [item["candidate_id"] for item in jackett if item["api_key_state"] != "available"],
        "jackett_indexer_sources": sorted({str(item.get("indexer_source")) for item in jackett if item.get("indexer_source")}),
        "jackett_indexers_missing_kind": [
            str(entry.get("id"))
            for item in jackett
            for entry in item.get("indexers", [])
            if entry.get("needs_kind_confirmation")
        ],
        "ambiguous": len(qb) > 1 or len(jackett) > 1,
    }
    save_json(output_dir / "discovery-report.json", report, 0o600)
    return report


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: discovery.py OUTPUT_DIR MEDIA_PARENT SECRETS_PATH", file=sys.stderr)
        return 2
    try:
        report = perform_discovery(Path(sys.argv[1]), sys.argv[2] or None, Path(sys.argv[3]))
    except (FpkError, OSError, json.JSONDecodeError) as exc:
        print(f"自动发现失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
