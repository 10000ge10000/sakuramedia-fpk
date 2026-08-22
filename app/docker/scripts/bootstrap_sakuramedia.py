#!/usr/bin/env python3
"""通过 SakuraMedia 已有 HTTP API 幂等初始化媒体库、下载器和 Indexer。"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from runtime_utils import FpkError, load_json, save_json


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token = ""

    def request(self, method: str, path: str, payload: Any = None, *, expected: tuple[int, ...] = (200,)) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                if response.status not in expected:
                    raise FpkError(f"API {method} {path} 返回 {response.status}")
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise FpkError(f"API {method} {path} 返回 {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            raise FpkError(f"无法访问 SakuraMedia API：{exc.reason}") from exc
        except OSError as exc:
            # 容器刚启动或 API 正在重启时，Linux 可能直接抛出
            # ConnectionResetError，而不是包装成 URLError；交给登录重试，
            # 不让一次瞬时断开终止整个 bootstrap。
            raise FpkError(f"无法访问 SakuraMedia API：{exc}") from exc

    def login(self, username: str, password: str) -> bool:
        try:
            result = self.request("POST", "/auth/tokens", {"username": username, "password": password}, expected=(201,))
        except FpkError:
            return False
        self.token = str(result["access_token"])
        return True


def wait_and_login(
    client: ApiClient,
    username: str,
    password: str,
    legacy_account: dict[str, Any] | None = None,
    timeout: int = 600,
) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.login(username, password):
            return "configured"
        legacy_username = str((legacy_account or {}).get("username") or "")
        legacy_password = str((legacy_account or {}).get("password") or "")
        if legacy_username and legacy_password and client.login(legacy_username, legacy_password):
            return "legacy"
        if (username, password) != ("account", "account") and client.login("account", "account"):
            return "default"
        time.sleep(5)
    raise FpkError("等待 SakuraMedia API 和数据库迁移完成超时。")


def ensure_account(
    client: ApiClient,
    login_state: str,
    username: str,
    password: str,
    legacy_account: dict[str, Any] | None = None,
) -> None:
    if login_state not in {"default", "legacy"}:
        return
    current_username = "account"
    current_password = "account"
    if login_state == "legacy":
        current_username = str((legacy_account or {}).get("username") or "")
        current_password = str((legacy_account or {}).get("password") or "")
    if username != current_username:
        client.request("PATCH", "/account", {"username": username})
    if password != current_password:
        client.request(
            "POST",
            "/account/password",
            {"current_password": current_password, "new_password": password},
            expected=(204,),
        )
    if not client.login(username, password):
        raise FpkError("初始账号修改后重新认证失败。")


def ensure_media_library(client: ApiClient) -> dict[str, Any]:
    libraries = client.request("GET", "/media-libraries")
    expected_path = "/mnt/media1/sakuramedia"
    for library in libraries:
        backend_config = library.get("backend_config") or {}
        root_path = backend_config.get("root_path") or library.get("root_path")
        if root_path == expected_path:
            return library
    # SakuraMedia v0.4.0+ 将本地媒体库改为 backend/backend_config 结构。
    # 只传上游当前要求的字段，避免旧版 root_path 顶层字段触发 422。
    return client.request(
        "POST",
        "/media-libraries",
        {
            "name": "SakuraMedia",
            "backend": "local",
            "backend_config": {"root_path": expected_path},
        },
        expected=(201,),
    )


def _select_candidate(items: list[dict[str, Any]], selected_id: str) -> tuple[dict[str, Any] | None, str | None]:
    if selected_id:
        selected = next((item for item in items if item.get("candidate_id") == selected_id), None)
        return selected, None if selected else f"未找到候选 ID：{selected_id}"
    if len(items) == 1:
        return items[0], None
    if len(items) > 1:
        return None, "发现多个候选实例，需要在配置向导填写候选 ID。"
    return None, "未发现候选实例。"


def _probe_indexer_url(torznab_url: str, api_key: str, timeout: int = 15) -> bool:
    """按上游搜索完全相同的参数形态探测单个 Indexer 是否可用。

    上游 jackett 客户端对任一 Indexer 的失败都会中断整个搜索，因此导入前
    必须过滤掉会 4xx/5xx/超时的站点。bootstrap 运行在宿主机上，需要把
    host.docker.internal 改写为 127.0.0.1。
    """
    host_url = torznab_url.replace("//host.docker.internal:", "//127.0.0.1:")
    separator = "&" if "?" in host_url else "?"
    probe_url = f"{host_url}{separator}t=search&q=test&apikey={urllib.parse.quote(api_key, safe='')}&cat=6000"
    try:
        with urllib.request.urlopen(probe_url, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _default_probe_batch(urls: list[str], api_key: str) -> dict[str, bool]:
    def probe(url: str) -> bool:
        return _probe_indexer_url(url, api_key)

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(probe, urls))
    return dict(zip(urls, results))


def ensure_download_client(
    client: ApiClient,
    config: dict[str, Any],
    secrets: dict[str, Any],
    discovery_dir: Path,
    library: dict[str, Any],
) -> dict[str, Any]:
    candidates = load_json(discovery_dir / "qbittorrent-candidates.json", []) or []
    selected, reason = _select_candidate(candidates, str(config.get("qb_candidate_id") or ""))
    manual = config.get("qb_manual") or {}
    if manual.get("base_url"):
        selected = {
            "candidate_id": "manual-qbittorrent",
            "container_name": "manual",
            "base_url": manual.get("base_url"),
            "username": manual.get("username", ""),
            "client_save_path": manual.get("client_save_path", ""),
            "path_mapping": {"local_path": manual.get("local_root_path", "")},
            "secret_ref": "manual-qbittorrent",
        }
        reason = None
    if not selected:
        return {"status": "skipped", "reason": reason}
    secret = (secrets.get("integrations") or {}).get(str(selected.get("secret_ref")), {})
    password = str(secret.get("password") or "")
    username = str(manual.get("username") or selected.get("username") or secret.get("username") or "")
    base_url = str(manual.get("base_url") or selected.get("base_url") or "")
    save_path = str(manual.get("client_save_path") or selected.get("client_save_path") or "")
    local_path = str(manual.get("local_root_path") or (selected.get("path_mapping") or {}).get("local_path") or "")
    if not all([base_url, username, password, save_path, local_path]):
        return {"status": "needs-input", "reason": "地址、用户名、密码或目录映射不完整。", "candidate_id": selected.get("candidate_id")}

    existing = client.request("GET", "/download-clients")
    canonical = base_url.rstrip("/")
    found = next((item for item in existing if str(item.get("base_url", "")).rstrip("/") == canonical), None)
    if found and config.get("config_action") != "redetect_update":
        return {"status": "kept", "client_id": found["id"]}

    probe_payload = {"base_url": base_url, "username": username, "password": password}
    probe = client.request("POST", "/download-clients/probe/test", probe_payload)
    if not probe.get("healthy"):
        return {"status": "probe-failed", "detail": probe.get("error")}
    storage_payload = {
        **probe_payload,
        "client_save_path": save_path,
        "local_root_path": local_path,
        "media_library_id": library["id"],
    }
    storage = client.request("POST", "/download-clients/probe/storage-test", storage_payload)
    if not storage.get("healthy"):
        return {"status": "storage-failed", "directory_mapping": storage.get("directory_mapping"), "hardlink": storage.get("hardlink")}
    write_payload = {
        "name": str(manual.get("name") or selected.get("container_name") or "qBittorrent"),
        **probe_payload,
        "client_save_path": save_path,
        "local_root_path": local_path,
        "media_library_id": library["id"],
    }
    if found:
        saved = client.request("PATCH", f"/download-clients/{found['id']}", write_payload)
        return {"status": "updated", "client_id": saved["id"]}
    saved = client.request("POST", "/download-clients", write_payload, expected=(201,))
    return {"status": "created", "client_id": saved["id"]}


def ensure_indexers(
    client: ApiClient,
    config: dict[str, Any],
    secrets: dict[str, Any],
    discovery_dir: Path,
    download_result: dict[str, Any],
    probe_batch: Callable[[list[str], str], dict[str, bool]] | None = None,
) -> dict[str, Any]:
    if not config.get("import_indexers", True):
        return {"status": "disabled"}
    client_id = download_result.get("client_id")
    if not client_id:
        return {"status": "skipped", "reason": "没有已验证的 qBittorrent 下载器。"}
    candidates = load_json(discovery_dir / "jackett-candidates.json", []) or []
    selected, reason = _select_candidate(candidates, str(config.get("jackett_candidate_id") or ""))
    manual = config.get("jackett_manual") or {}
    if manual.get("base_url"):
        if selected is None:
            selected = {"candidate_id": "manual-jackett", "base_url": manual["base_url"], "indexers": [], "secret_ref": "manual-jackett"}
        else:
            selected = dict(selected)
            selected["base_url"] = manual["base_url"]
        reason = None
    if not selected:
        return {"status": "skipped", "reason": reason}
    secret = (secrets.get("integrations") or {}).get(str(selected.get("secret_ref")), {})
    api_key = str(secret.get("api_key") or "")
    if not api_key:
        return {"status": "needs-input", "reason": "Jackett API Key 不可用。"}
    current = client.request("GET", "/indexer-settings")
    # v0.4.17+ 索引器配置整体落库并按 Torznab 端点逐站鉴权；PATCH 传入
    # indexers 时是整表替换，现有条目必须原样回传（含各自 api_key），
    # 否则会清掉用户手动维护的站点和密钥。
    known_urls: dict[str, str] = {}
    for item in selected.get("indexers") or []:
        url = str(item.get("torznab_url") or "").rstrip("/")
        if url:
            known_urls[url] = api_key
    merged: list[dict[str, Any]] = []
    used_names: set[str] = set()

    def unique_name(raw: str, fallback: str) -> str:
        base = str(raw or fallback).strip() or fallback
        name = base
        suffix = 2
        while name in used_names:
            name = f"{base}-{suffix}"
            suffix += 1
        used_names.add(name)
        return name

    for item in current.get("indexers", []):
        bound_clients = item.get("download_clients") or []
        client_ids = [entry.get("id") for entry in bound_clients if entry.get("id")]
        if not client_ids and item.get("download_client_id"):
            client_ids = [item["download_client_id"]]
        if not client_ids:
            # 服务端要求每个索引器至少绑定一个下载器；历史残缺数据绑定
            # 当前已验证的下载器，避免整表替换提交失败。
            client_ids = [client_id]
        url = str(item.get("url", "")).rstrip("/")
        # 旧版（全局 api_key 时代）由本包导入的站点升级后 api_key 为空；
        # 仅对仍由当前 Jackett 候选提供的 URL 补齐密钥，其余站点不动。
        existing_key = item.get("api_key")
        if not existing_key and url in known_urls:
            existing_key = api_key
        merged.append(
            {
                "name": unique_name(item.get("name"), url),
                "url": item.get("url"),
                "kind": item.get("kind"),
                "api_key": existing_key,
                "download_client_ids": client_ids,
            }
        )
    existing_urls = {str(item.get("url", "")).rstrip("/") for item in current.get("indexers", [])}
    skipped_unknown: list[str] = []
    skipped_unhealthy: list[str] = []
    pending: list[tuple[dict[str, Any], str, str]] = []
    for item in selected.get("indexers") or []:
        url = str(item.get("torznab_url") or "").rstrip("/")
        kind = str(item.get("kind") or "")
        if not url or not kind:
            skipped_unknown.append(str(item.get("id") or item.get("name") or "unknown"))
            continue
        if url in existing_urls:
            continue
        pending.append((item, url, kind))
    if pending:
        # 上游搜索遇到任一失败 Indexer 会整体中断，新增导入前并发探测过滤；
        # 被过滤的站点保留在报告里，下次配置运行会重新探测。
        probe_results = (probe_batch or _default_probe_batch)([url for _, url, _ in pending], api_key)
        for item, url, kind in pending:
            if probe_results.get(url):
                merged.append(
                    {
                        "name": unique_name(item.get("name"), item.get("id") or url),
                        "url": url,
                        "kind": kind,
                        "api_key": api_key,
                        "download_client_ids": [client_id],
                    }
                )
                existing_urls.add(url)
            else:
                skipped_unhealthy.append(str(item.get("name") or item.get("id") or url))
    snapshot = discovery_dir / f"sakuramedia-indexers-before-{int(time.time())}.json"
    save_json(snapshot, current, 0o600)
    updated = client.request("PATCH", "/indexer-settings", {"indexers": merged})
    test = client.request("GET", "/indexer-settings/test")
    # 上游错误信息可能回显带 apikey 的完整 URL，写入报告前必须脱敏。
    test_detail = ""
    error = test.get("error") or {}
    if error:
        test_detail = re.sub(r"apikey=[^&\s'\"]+", "apikey=***", str(error.get("message") or ""))
    return {
        "status": "updated",
        "indexer_count": len(updated.get("indexers", [])),
        "connection_healthy": bool(test.get("healthy")),
        "connection_detail": test_detail or None,
        "skipped_unknown_kind": skipped_unknown,
        "skipped_unhealthy": skipped_unhealthy,
    }


def bootstrap(data_root: Path, timeout: int = 600) -> dict[str, Any]:
    config = load_json(data_root / "config" / "fpk-config.json", {}) or {}
    secrets = load_json(data_root / "config" / "fpk-secrets.json", {}) or {}
    account = secrets.get("sakuramedia_account") or {}
    username = str(account.get("username") or "")
    password = str(account.get("password") or "")
    legacy_account = secrets.get("sakuramedia_legacy_account") or None
    if not username or not password:
        raise FpkError("SakuraMedia 初始账号未配置。")
    client = ApiClient(f"http://127.0.0.1:{config.get('api_port', 38000)}")
    state = wait_and_login(client, username, password, legacy_account, timeout)
    ensure_account(client, state, username, password, legacy_account)
    if state in {"default", "legacy"} and legacy_account:
        secrets.pop("sakuramedia_legacy_account", None)
        save_json(data_root / "config" / "fpk-secrets.json", secrets, 0o600)
    library = ensure_media_library(client)
    discovery_dir = data_root / "integration-discovery"
    download_result = ensure_download_client(client, config, secrets, discovery_dir, library)
    indexer_result = ensure_indexers(client, config, secrets, discovery_dir, download_result)
    report = {
        "completed_at": int(time.time()),
        "media_library_id": library["id"],
        "download_client": download_result,
        "indexers": indexer_result,
    }
    save_json(data_root / "config" / "bootstrap-state.json", report, 0o600)
    save_json(discovery_dir / "bootstrap-report.json", report, 0o600)
    return report


def merge_indexers(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """供测试复用的幂等 URL 合并函数。"""
    result = list(existing)
    seen = {str(item.get("url", "")).rstrip("/") for item in existing}
    for item in additions:
        key = str(item.get("url", "")).rstrip("/")
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in {2, 3}:
        print("usage: bootstrap_sakuramedia.py DATA_ROOT [TIMEOUT]", file=sys.stderr)
        raise SystemExit(2)
    try:
        result = bootstrap(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) == 3 else 600)
    except (FpkError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SakuraMedia 自动初始化失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False))
