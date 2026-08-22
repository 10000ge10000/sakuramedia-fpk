# 项目目录树

```text
sakuramedia-fnos-fpk/
├── app/
│   ├── docker/
│   │   ├── scripts/
│   │   │   ├── bootstrap_sakuramedia.py
│   │   │   ├── discover-jackett.sh
│   │   │   ├── discover-qbittorrent.sh
│   │   │   ├── discovery.py
│   │   │   ├── joytag-entrypoint.sh
│   │   │   ├── lifecycle.py
│   │   │   ├── postgres-entrypoint.sh
│   │   │   └── runtime_utils.py
│   │   ├── build-info.json
│   │   └── docker-compose.yaml
│   └── ui/
│       ├── images/
│       │   ├── icon_64.png
│       │   └── icon_256.png
│       └── config
├── cmd/
│   ├── config_callback
│   ├── config_init
│   ├── install_callback
│   ├── install_init
│   ├── main
│   ├── runtime.sh
│   ├── uninstall_callback
│   ├── uninstall_init
│   ├── upgrade_callback
│   └── upgrade_init
├── config/
│   ├── privilege
│   └── resource
├── dist/
│   ├── sakuramedia-1.0.3.fpk
│   └── sakuramedia-1.0.3.fpk.sha256
├── docs/
│   ├── DISCOVERY.md
│   ├── INSTALL.md
│   ├── PROJECT-TREE.md
│   ├── TROUBLESHOOTING.md
│   └── UPGRADE-UNINSTALL.md
├── scripts/
│   ├── discover-jackett.sh
│   ├── discover-qbittorrent.sh
│   └── inspect-fpk.py
├── tests/
│   ├── compose-full.env
│   ├── compose-light.env
│   ├── test_bootstrap.py
│   ├── test_discovery.py
│   └── test_lifecycle_config.py
├── wizard/
│   ├── config
│   ├── install
│   ├── uninstall
│   └── upgrade
├── AGENTS.md
├── build.sh
├── CHANGELOG.md
├── ICON.PNG
├── ICON_256.PNG
├── LICENSE
├── manifest
├── README.md
├── TASKS.md
├── TEST_REPORT.md
└── verify.sh
```

`.build/` 是 `build.sh` 的 fnpack 校验缓存，不进入 FPK；Python `__pycache__` 也不会写入源码或构建产物。
