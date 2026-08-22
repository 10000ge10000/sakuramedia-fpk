from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "app" / "docker" / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from lifecycle import build_config, resolve_data_root  # noqa: E402


class LifecycleConfigTests(unittest.TestCase):
    def test_blank_optional_data_dir_uses_managed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {"TRIM_PKGVAR": tmp, "wizard_data_dir": ""},
                clear=False,
            ):
                os.environ.pop("wizard_data_mode", None)
                result = resolve_data_root({})
            self.assertEqual(result, (Path(tmp) / "sakuramedia-data").resolve())

    def test_custom_data_dir_works_without_legacy_mode_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "中文 数据"
            with patch.dict(
                os.environ,
                {"TRIM_PKGVAR": tmp, "wizard_data_dir": str(custom)},
                clear=False,
            ):
                os.environ.pop("wizard_data_mode", None)
                result = resolve_data_root({})
            self.assertEqual(result, custom.resolve())

    def test_existing_custom_path_survives_config_without_data_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = {"data_mode": "custom", "data_root": str(Path(tmp) / "旧数据")}
            with patch.dict(os.environ, {"TRIM_PKGVAR": tmp}, clear=False):
                os.environ.pop("wizard_data_mode", None)
                os.environ.pop("wizard_data_dir", None)
                result = resolve_data_root(existing)
            self.assertEqual(result, Path(existing["data_root"]).resolve())

    def test_quick_install_uses_runtime_defaults_when_advanced_fields_are_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "媒体目录"
            media.mkdir()
            values = {
                "TRIM_PKGVAR": tmp,
                "wizard_data_dir": "",
                "wizard_media_parent": str(media),
                "COMPOSE_PROFILES": "light",
                "wizard_api_port": "38000",
                "wizard_web_port": "38080",
                "wizard_puid": "",
                "wizard_pgid": "",
                "wizard_timezone": "",
            }
            with patch.dict(os.environ, values, clear=False):
                os.environ.pop("wizard_data_mode", None)
                config, secrets = build_config({})
            self.assertEqual(config["puid"], 1000)
            self.assertEqual(config["pgid"], 1000)
            self.assertEqual(config["timezone"], "Asia/Shanghai")
            self.assertEqual(config["data_mode"], "managed")
            self.assertEqual(
                secrets["sakuramedia_account"],
                {"username": "yiwan", "password": "yiwan123"},
            )

    def test_existing_account_is_staged_for_one_time_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "sakuramedia-data"
            config_dir = data_root / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "fpk-secrets.json").write_text(
                '{"sakuramedia_account":{"username":"old-user","password":"old-secret"}}',
                encoding="utf-8",
            )
            media = Path(tmp) / "媒体目录"
            media.mkdir()
            values = {
                "TRIM_PKGVAR": tmp,
                "wizard_data_dir": "",
                "wizard_media_parent": str(media),
                "COMPOSE_PROFILES": "light",
                "wizard_api_port": "38000",
                "wizard_web_port": "38080",
            }
            with patch.dict(os.environ, values, clear=False):
                os.environ.pop("wizard_data_mode", None)
                _, secrets = build_config({})
            self.assertEqual(secrets["sakuramedia_account"], {"username": "yiwan", "password": "yiwan123"})
            self.assertEqual(
                secrets["sakuramedia_legacy_account"],
                {"username": "old-user", "password": "old-secret"},
            )


if __name__ == "__main__":
    unittest.main()
