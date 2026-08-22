from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "app" / "docker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from discovery import discover_from_inspects, map_container_path  # noqa: E402


def container(
    name: str,
    image: str,
    *,
    env: list[str] | None = None,
    mounts: list[dict] | None = None,
    ports: dict | None = None,
    networks: list[str] | None = None,
) -> dict:
    return {
        "Id": (name * 64)[:64],
        "Name": f"/{name}",
        "Config": {"Image": image, "Env": env or [], "Labels": {}},
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
        "Mounts": mounts or [],
        "NetworkSettings": {
            "Ports": ports or {},
            "Networks": {item: {} for item in (networks or ["bridge"])},
        },
    }


class DiscoveryTests(unittest.TestCase):
    def test_01_no_qbittorrent_or_jackett(self):
        qb, jackett, secrets = discover_from_inspects([container("redis", "redis:8")])
        self.assertEqual((qb, jackett, secrets), ([], [], {}))

    def test_02_single_qbittorrent(self):
        inspect = container("pt-client", "linuxserver/qbittorrent:5", env=["WEBUI_PORT=8080"])
        qb, _, _ = discover_from_inspects([inspect])
        self.assertEqual(len(qb), 1)

    def test_03_multiple_qbittorrent(self):
        data = [container("bt", "hotio/qbittorrent"), container("pt", "qbittorrent-nox:latest")]
        qb, _, _ = discover_from_inspects(data)
        self.assertEqual(len(qb), 2)
        self.assertNotEqual(qb[0]["candidate_id"], qb[1]["candidate_id"])

    def test_04_plaintext_password_from_environment(self):
        inspect = container(
            "qb",
            "custom/media-client",
            env=["WEBUI_PORT=8080", "QBITTORRENT_USERNAME=user", "QBITTORRENT_PASSWORD=secret"],
        )
        qb, _, secrets = discover_from_inspects([inspect])
        self.assertEqual(qb[0]["password_state"], "plaintext-available")
        self.assertEqual(secrets[qb[0]["candidate_id"]]["password"], "secret")

    def test_05_hash_password_is_not_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conf = root / "qBittorrent" / "config" / "qBittorrent.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text(
                "[Preferences]\nDownloads\\SavePath=/downloads/\nWebUI\\Password_PBKDF2=@ByteArray(hash)\n",
                encoding="utf-8",
            )
            inspect = container(
                "qb",
                "superng6/qbittorrent:latest",
                mounts=[{"Type": "bind", "Source": str(root), "Destination": "/config", "RW": True}],
            )
            qb, _, secrets = discover_from_inspects([inspect])
            self.assertEqual(qb[0]["password_state"], "hash-only")
            self.assertEqual(secrets[qb[0]["candidate_id"]]["password"], "")

    def test_06_unpublished_port_keeps_networks(self):
        inspect = container("qb", "qbittorrent-nox", networks=["torrent", "bridge"])
        qb, _, _ = discover_from_inspects([inspect])
        self.assertIsNone(qb[0]["published_port"])
        self.assertEqual(qb[0]["networks"], ["bridge", "torrent"])

    def test_07_single_jackett(self):
        _, jackett, _ = discover_from_inspects([container("index-service", "linuxserver/jackett")])
        self.assertEqual(len(jackett), 1)

    def test_08_multiple_jackett(self):
        data = [container("jackett-a", "hotio/jackett"), container("jackett-b", "jackett/jackett")]
        _, jackett, _ = discover_from_inspects(data)
        self.assertEqual(len(jackett), 2)

    def test_09_jackett_api_key_is_kept_only_in_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Jackett").mkdir()
            (root / "Jackett" / "ServerConfig.json").write_text(json.dumps({"APIKey": "1234567890abcdef"}), encoding="utf-8")
            inspect = container("jackett", "linuxserver/jackett", mounts=[{"Source": str(root), "Destination": "/config", "RW": True}])
            _, jackett, secrets = discover_from_inspects([inspect])
            candidate = jackett[0]
            self.assertNotIn("1234567890abcdef", json.dumps(candidate))
            self.assertEqual(secrets[candidate["candidate_id"]]["api_key"], "1234567890abcdef")

    def test_10_jackett_missing_api_key(self):
        _, jackett, secrets = discover_from_inspects([container("jackett", "linuxserver/jackett")])
        self.assertEqual(jackett[0]["api_key_state"], "missing")
        self.assertEqual(secrets[jackett[0]["candidate_id"]]["api_key"], "")

    def test_jackett_list_style_indexer_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexers = root / "Jackett" / "Indexers"
            indexers.mkdir(parents=True)
            (root / "Jackett" / "ServerConfig.json").write_text(json.dumps({"APIKey": "test-key"}), encoding="utf-8")
            (indexers / "example.json").write_text(
                json.dumps([{"id": "name", "value": "示例索引器"}, {"id": "type", "value": "private"}]),
                encoding="utf-8",
            )
            inspect = container("jackett", "linuxserver/jackett", mounts=[{"Source": str(root), "Destination": "/config", "RW": True}])
            _, jackett, _ = discover_from_inspects([inspect])
            self.assertEqual(jackett[0]["indexers"][0]["name"], "示例索引器")
            self.assertEqual(jackett[0]["indexers"][0]["kind"], "pt")

    def test_jackett_real_list_style_config_has_no_kind_without_api(self):
        # 真实 Jackett 列表型配置的 type 字段是控件类型，文件兜底路径不应误判 kind。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexers = root / "Jackett" / "Indexers"
            indexers.mkdir(parents=True)
            (root / "Jackett" / "ServerConfig.json").write_text(json.dumps({"APIKey": "test-key"}), encoding="utf-8")
            (indexers / "0magnet.json").write_text(
                json.dumps([{"id": "sitelink", "type": "inputstring", "value": "https://13mag.net/"}]),
                encoding="utf-8",
            )
            inspect = container(
                "jackett",
                "linuxserver/jackett",
                mounts=[{"Source": str(root), "Destination": "/config", "RW": True}],
                ports={"9117/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9117"}]},
            )
            _, jackett, _ = discover_from_inspects([inspect])
            self.assertEqual(jackett[0]["indexer_source"], "config-files")
            self.assertIsNone(jackett[0]["indexers"][0]["kind"])
            self.assertTrue(jackett[0]["indexers"][0]["needs_kind_confirmation"])

    def test_jackett_torznab_catalog_provides_kinds(self):
        catalog_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<indexers>'
            '<indexer id="yts" configured="true"><title>YTS</title><type>public</type></indexer>'
            '<indexer id="alpharatio" configured="true"><title>AlphaRatio</title><type>private</type></indexer>'
            '<indexer id="anisource" configured="true"><title>AniSource</title><type>semi-private</type></indexer>'
            '<indexer id="unconfigured" configured="false"><title>Other</title><type>public</type></indexer>'
            "</indexers>"
        )
        requested: list[str] = []

        def fake_http_get(url: str) -> str | None:
            requested.append(url)
            return catalog_xml

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexers = root / "Jackett" / "Indexers"
            indexers.mkdir(parents=True)
            (root / "Jackett" / "ServerConfig.json").write_text(json.dumps({"APIKey": "secret-key"}), encoding="utf-8")
            # 文件路径里还有一个 API 目录之外的 Indexer，应保留为兜底候选。
            (indexers / "legacy.json").write_text(
                json.dumps([{"id": "name", "value": "旧站点"}, {"id": "type", "value": "public"}]),
                encoding="utf-8",
            )
            inspect = container(
                "jackett",
                "linuxserver/jackett",
                mounts=[{"Source": str(root), "Destination": "/config", "RW": True}],
                ports={"9117/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9117"}]},
            )
            _, jackett, secrets = discover_from_inspects([inspect], http_fetch=fake_http_get)
            candidate = jackett[0]
            self.assertEqual(candidate["indexer_source"], "torznab-api")
            kinds = {item["id"]: item["kind"] for item in candidate["indexers"]}
            self.assertEqual(kinds["yts"], "bt")
            self.assertEqual(kinds["alpharatio"], "pt")
            self.assertEqual(kinds["anisource"], "pt")
            self.assertNotIn("unconfigured", kinds)
            self.assertEqual(kinds["legacy"], "bt")
            urls = {item["id"]: item["torznab_url"] for item in candidate["indexers"]}
            self.assertEqual(urls["yts"], "http://host.docker.internal:9117/api/v2.0/indexers/yts/results/torznab/api")
            # apikey 只允许出现在请求 URL 和秘密文件中。
            self.assertEqual(len(requested), 1)
            self.assertIn("apikey=secret-key", requested[0])
            self.assertNotIn("secret-key", json.dumps(candidate))
            self.assertEqual(secrets[candidate["candidate_id"]]["api_key"], "secret-key")

    def test_jackett_torznab_catalog_unreachable_falls_back_to_files(self):
        def broken_http_get(url: str) -> str | None:
            return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            indexers = root / "Jackett" / "Indexers"
            indexers.mkdir(parents=True)
            (root / "Jackett" / "ServerConfig.json").write_text(json.dumps({"APIKey": "k"}), encoding="utf-8")
            (indexers / "a.json").write_text(json.dumps([{"id": "type", "value": "private"}]), encoding="utf-8")
            inspect = container(
                "jackett",
                "linuxserver/jackett",
                mounts=[{"Source": str(root), "Destination": "/config", "RW": True}],
                ports={"9117/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9117"}]},
            )
            _, jackett, _ = discover_from_inspects([inspect], http_fetch=broken_http_get)
            self.assertEqual(jackett[0]["indexer_source"], "config-files")
            self.assertEqual(jackett[0]["indexers"][0]["kind"], "pt")

    def test_11_download_mapping_longest_mount(self):
        mounts = [
            {"Source": "/vol2/media", "Destination": "/data", "RW": True},
            {"Source": "/vol2/media/downloads", "Destination": "/data/downloads", "RW": True},
        ]
        result = map_container_path("/data/downloads/pt", mounts, "/vol2/media")
        self.assertEqual(result["host_path"], str(Path("/vol2/media/downloads/pt")))
        self.assertEqual(result["local_path"], "/mnt/media1/downloads/pt")

    def test_12_cross_volume_is_not_falsely_mapped(self):
        mounts = [{"Source": "/vol1/downloads", "Destination": "/downloads", "RW": True}]
        result = map_container_path("/downloads", mounts, "/vol2/media")
        self.assertEqual(result["status"], "outside-media-parent")

    def test_13_vol1_and_vol2_are_distinct(self):
        mounts = [{"Source": "/vol2/1000/media", "Destination": "/downloads", "RW": True}]
        self.assertEqual(map_container_path("/downloads", mounts, "/vol1/1000/media")["status"], "outside-media-parent")

    def test_14_chinese_and_space_path(self):
        mounts = [{"Source": "/vol2/1000/影视 资料/下载", "Destination": "/downloads", "RW": True}]
        result = map_container_path("/downloads/新建 文件夹", mounts, "/vol2/1000/影视 资料")
        self.assertEqual(result["local_path"], "/mnt/media1/下载/新建 文件夹")

    def test_15_read_only_mount_is_reported(self):
        mounts = [{"Source": "/vol2/media/downloads", "Destination": "/downloads", "RW": False}]
        result = map_container_path("/downloads", mounts, "/vol2/media")
        self.assertTrue(result["mount_read_only"])


if __name__ == "__main__":
    unittest.main()
