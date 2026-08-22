from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "app" / "docker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bootstrap_sakuramedia import (  # noqa: E402
    ensure_account,
    ensure_indexers,
    ensure_media_library,
    merge_indexers,
)


class BootstrapTests(unittest.TestCase):
    def test_repeated_initialization_does_not_duplicate_indexers(self):
        existing = [{"name": "A", "url": "http://jackett/a", "kind": "bt", "download_client_id": 1}]
        additions = [
            {"name": "A2", "url": "http://jackett/a/", "kind": "bt", "download_client_id": 1},
            {"name": "B", "url": "http://jackett/b", "kind": "pt", "download_client_id": 1},
        ]
        once = merge_indexers(existing, additions)
        twice = merge_indexers(once, additions)
        self.assertEqual(len(once), 2)
        self.assertEqual(once, twice)

    def test_legacy_account_migration_uses_old_password_once(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                return None

            def login(self, username, password):
                self.calls.append(("login", username, password))
                return True

        client = FakeClient()
        ensure_account(
            client,
            "legacy",
            "yiwan",
            "yiwan123",
            {"username": "old-user", "password": "old-secret"},
        )
        self.assertIn(("PATCH", "/account", {"username": "yiwan"}), client.calls)
        self.assertIn(
            (
                "POST",
                "/account/password",
                {"current_password": "old-secret", "new_password": "yiwan123"},
            ),
            client.calls,
        )

    def test_media_library_uses_v04_backend_shape(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                if method == "GET":
                    return []
                return {"id": 1, "backend": "local", "backend_config": {"root_path": "/mnt/media1/sakuramedia"}}

        client = FakeClient()
        library = ensure_media_library(client)
        self.assertEqual(library["id"], 1)
        self.assertEqual(
            client.calls[-1],
            (
                "POST",
                "/media-libraries",
                {
                    "name": "SakuraMedia",
                    "backend": "local",
                    "backend_config": {"root_path": "/mnt/media1/sakuramedia"},
                },
            ),
        )

    def test_indexer_payload_uses_v04_multi_client_binding(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                if path == "/indexer-settings" and method == "GET":
                    return {
                        "indexers": [
                            {
                                "name": "Existing",
                                "url": "http://jackett/existing",
                                "kind": "bt",
                                "api_key": None,
                                "download_clients": [{"id": 3, "name": "old-qb", "kind": "qbittorrent"}],
                            }
                        ]
                    }
                if path == "/indexer-settings" and method == "PATCH":
                    return {"indexers": payload["indexers"]}
                if path == "/indexer-settings/test":
                    return {"healthy": True}
                raise AssertionError(f"unexpected request: {method} {path}")

        with tempfile.TemporaryDirectory() as tmp:
            discovery_dir = Path(tmp)
            (discovery_dir / "jackett-candidates.json").write_text(
                json.dumps(
                    [
                        {
                            "candidate_id": "jk-1",
                            "base_url": "http://jackett:9117",
                            "secret_ref": "jk-1",
                            "indexers": [
                                {
                                    "id": "new",
                                    "name": "New",
                                    "kind": "pt",
                                    "torznab_url": "http://jackett/new",
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            client = FakeClient()
            result = ensure_indexers(
                client,
                {"import_indexers": True, "jackett_candidate_id": "jk-1", "config_action": "keep"},
                {"integrations": {"jk-1": {"api_key": "secret"}}},
                discovery_dir,
                {"client_id": 7},
                probe_batch=lambda urls, key: {url: True for url in urls},
            )
            self.assertEqual(result["status"], "updated")
            patch_call = next(call for call in client.calls if call[0] == "PATCH")
            # v0.4.17+：请求体只带 indexers，鉴权改为逐站 api_key
            self.assertEqual(set(patch_call[2].keys()), {"indexers"})
            indexers = patch_call[2]["indexers"]
            self.assertEqual(indexers[0]["download_client_ids"], [3])
            self.assertIsNone(indexers[0]["api_key"])
            self.assertEqual(indexers[1]["download_client_ids"], [7])
            self.assertEqual(indexers[1]["api_key"], "secret")

    def test_legacy_indexer_from_our_jackett_gets_key_backfilled(self):
        """旧版全局 api_key 时代导入的站点，升级后逐站 key 为空时仅对已知 URL 补齐。"""

        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                if path == "/indexer-settings" and method == "GET":
                    return {
                        "indexers": [
                            {"name": "Ours", "url": "http://jackett/ours", "kind": "bt", "api_key": None, "download_clients": [{"id": 7}]},
                            {"name": "Manual", "url": "http://othersite/torznab", "kind": "pt", "api_key": None, "download_clients": [{"id": 7}]},
                        ]
                    }
                if path == "/indexer-settings" and method == "PATCH":
                    return {"indexers": payload["indexers"]}
                if path == "/indexer-settings/test":
                    return {"healthy": True}
                raise AssertionError(f"unexpected request: {method} {path}")

        with tempfile.TemporaryDirectory() as tmp:
            discovery_dir = Path(tmp)
            (discovery_dir / "jackett-candidates.json").write_text(
                json.dumps(
                    [
                        {
                            "candidate_id": "jk-1",
                            "base_url": "http://jackett:9117",
                            "secret_ref": "jk-1",
                            "indexers": [
                                {"id": "ours", "name": "Ours", "kind": "bt", "torznab_url": "http://jackett/ours"}
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            client = FakeClient()
            ensure_indexers(
                client,
                {"import_indexers": True, "jackett_candidate_id": "jk-1", "config_action": "keep"},
                {"integrations": {"jk-1": {"api_key": "secret"}}},
                discovery_dir,
                {"client_id": 7},
                probe_batch=lambda urls, key: {url: True for url in urls},
            )
            patch_call = next(call for call in client.calls if call[0] == "PATCH")
            by_url = {item["url"]: item for item in patch_call[2]["indexers"]}
            self.assertEqual(by_url["http://jackett/ours"]["api_key"], "secret")
            # 非本包管理的站点保持原状（空 key 不动）
            self.assertIsNone(by_url["http://othersite/torznab"]["api_key"])

    def test_duplicate_indexer_names_are_made_unique(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                if path == "/indexer-settings" and method == "GET":
                    return {"indexers": []}
                if path == "/indexer-settings" and method == "PATCH":
                    return {"indexers": payload["indexers"]}
                if path == "/indexer-settings/test":
                    return {"healthy": True}
                raise AssertionError(f"unexpected request: {method} {path}")

        with tempfile.TemporaryDirectory() as tmp:
            discovery_dir = Path(tmp)
            (discovery_dir / "jackett-candidates.json").write_text(
                json.dumps(
                    [
                        {
                            "candidate_id": "jk-1",
                            "base_url": "http://jackett:9117",
                            "secret_ref": "jk-1",
                            "indexers": [
                                {"id": "a", "name": "Same", "kind": "bt", "torznab_url": "http://jackett/a"},
                                {"id": "b", "name": "Same", "kind": "bt", "torznab_url": "http://jackett/b"},
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            client = FakeClient()
            ensure_indexers(
                client,
                {"import_indexers": True, "jackett_candidate_id": "jk-1", "config_action": "keep"},
                {"integrations": {"jk-1": {"api_key": "k"}}},
                discovery_dir,
                {"client_id": 7},
                probe_batch=lambda urls, key: {url: True for url in urls},
            )
            patch_call = next(call for call in client.calls if call[0] == "PATCH")
            names = [item["name"] for item in patch_call[2]["indexers"]]
            self.assertEqual(len(names), len(set(names)))

    def test_indexer_test_error_detail_is_redacted(self):
        class FakeClient:
            def request(self, method, path, payload=None, **kwargs):
                if path == "/indexer-settings" and method == "GET":
                    return {"indexers": []}
                if path == "/indexer-settings" and method == "PATCH":
                    return {"indexers": payload["indexers"]}
                if path == "/indexer-settings/test":
                    return {
                        "healthy": False,
                        "error": {
                            "type": "torznab_request_error",
                            "message": "Client error '400' for url 'http://jackett/api?t=search&apikey=topsecret&cat=6000'",
                        },
                    }
                raise AssertionError(f"unexpected request: {method} {path}")

        with tempfile.TemporaryDirectory() as tmp:
            discovery_dir = Path(tmp)
            (discovery_dir / "jackett-candidates.json").write_text(
                json.dumps(
                    [
                        {
                            "candidate_id": "jk-1",
                            "base_url": "http://jackett:9117",
                            "secret_ref": "jk-1",
                            "indexers": [],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            result = ensure_indexers(
                FakeClient(),
                {"import_indexers": True, "jackett_candidate_id": "jk-1", "config_action": "keep"},
                {"integrations": {"jk-1": {"api_key": "topsecret"}}},
                discovery_dir,
                {"client_id": 7},
            )
            self.assertFalse(result["connection_healthy"])
            self.assertIn("apikey=***", result["connection_detail"])
            self.assertNotIn("topsecret", result["connection_detail"])

    def test_unhealthy_indexers_are_not_imported(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, path, payload=None, **kwargs):
                self.calls.append((method, path, payload))
                if path == "/indexer-settings" and method == "GET":
                    return {"indexers": []}
                if path == "/indexer-settings" and method == "PATCH":
                    return {"indexers": payload["indexers"]}
                if path == "/indexer-settings/test":
                    return {"healthy": True}
                raise AssertionError(f"unexpected request: {method} {path}")

        def fake_probe_batch(urls, api_key):
            return {url: url.endswith("/good") for url in urls}

        with tempfile.TemporaryDirectory() as tmp:
            discovery_dir = Path(tmp)
            (discovery_dir / "jackett-candidates.json").write_text(
                json.dumps(
                    [
                        {
                            "candidate_id": "jk-1",
                            "base_url": "http://jackett:9117",
                            "secret_ref": "jk-1",
                            "indexers": [
                                {"id": "good", "name": "Good", "kind": "bt", "torznab_url": "http://jackett/good"},
                                {"id": "bad", "name": "Bad", "kind": "bt", "torznab_url": "http://jackett/bad"},
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            client = FakeClient()
            result = ensure_indexers(
                client,
                {"import_indexers": True, "jackett_candidate_id": "jk-1", "config_action": "keep"},
                {"integrations": {"jk-1": {"api_key": "k"}}},
                discovery_dir,
                {"client_id": 7},
                probe_batch=fake_probe_batch,
            )
            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["skipped_unhealthy"], ["Bad"])
            patch_call = next(call for call in client.calls if call[0] == "PATCH")
            imported_urls = [item["url"] for item in patch_call[2]["indexers"]]
            self.assertEqual(imported_urls, ["http://jackett/good"])


if __name__ == "__main__":
    unittest.main()
