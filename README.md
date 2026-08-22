# SakuraMedia fnOS FPK

[![Blog](https://img.shields.io/badge/Blog-910501.xyz-orange)](https://blog.910501.xyz/)
[![Bilibili](https://img.shields.io/badge/B%E7%AB%99-59438380-00a1d6?logo=bilibili)](https://space.bilibili.com/59438380)
[![YouTube](https://img.shields.io/badge/YouTube-10000%20AI%20Share-ff0000?logo=youtube&logoColor=white)](https://www.youtube.com/channel/UCqgvZnCN9-9pZcL4SWxmnDw)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)

将 [SakuraMedia](https://github.com/tinypinglite/sakuramedia) 和 [SakuraMediaBE](https://github.com/tinypinglite/sakuramediabe) 封装为可由飞牛 fnOS 应用中心安装、启停、配置和升级的第三方 FPK。

> 注意：这是非官方第三方适配包。SakuraMedia 上游明确标注为实验性项目，请先备份重要数据，不要直接用于唯一副本。

## 特性

- 轻量模式：PostgreSQL、SakuraMedia 后端、Web。
- 完整模式：在轻量模式基础上增加 JoyTag Infer 和 Qdrant。
- 已同步官方前端 `v0.4.13`、后端 `v0.4.21`，并锁定多架构镜像 digest。
- 用户可在快速安装中填写自定义数据目录；留空使用应用中心托管目录，媒体路径不写死 `/vol1/1000`。
- 自动发现 Docker 中的 qBittorrent 和 Jackett，不依赖固定容器名。
- 通过 SakuraMedia HTTP API创建媒体库、验证下载目录、硬链接并导入 Indexer。
- 随机数据库密码、敏感文件 `600`、日志脱敏，不修改外部容器。
- 支持 fnOS 应用中心启动、停止、状态检查、配置、升级和保留数据卸载。

## 快速开始

### 通过 FnDepot 安装（推荐）

1. 在飞牛应用中心安装 FnDepot（第三方应用仓库工具）。
2. 打开 FnDepot 的【源管理】→【添加源】，填入本项目的源地址：

```text
https://10000ge10000.github.io/sakuramedia-fpk/fnpack.json
```

3. 在 FnDepot 中找到 SakuraMedia，一键安装和更新。FPK 内部使用 Docker 多架构镜像，x86_64 与 ARM64 设备通用。

### 手动安装 FPK

1. 打开 fnOS 的“应用中心”。
2. 选择“手动安装”，上传 [Releases](https://github.com/10000ge10000/sakuramedia-fpk/releases/latest) 中的 `sakuramedia-<版本>.fpk`（或本地 `dist/` 构建产物）。
3. 在唯一的“快速安装”步骤中选择轻量或完整模式，填写媒体父目录；数据目录留空即可使用应用中心托管目录。
4. 确认 API/Web 端口（默认 `38000`/`38080`）。
5. 安装完成后使用固定账号登录：用户名 `yiwan`，密码 `yiwan123`。

安装完成后，桌面图标打开：

```text
http://{NAS_IP}:{WEB_PORT}
```

SakuraMedia 上游 Web 登录页首次使用仍要求填写后端地址，请填 `http://{NAS_IP}:{API_PORT}`；该地址会由上游客户端保存在浏览器中。本 FPK 不修改上游前端代码。

首次安装不再要求填写账号、PUID、PGID、时区、qBittorrent 或 Jackett 参数。账号按用户要求固定为 `yiwan/yiwan123`，其余项目使用默认值或在安装后自动发现。已有安装升级时保留原账号，避免升级后无法登录。需要补充集成密码、多实例候选或手动地址时，再打开 fnOS 的“配置”向导。

> 安全提醒：`yiwan123` 是固定弱密码，仅按本次部署要求设置；如果应用暴露到可信网络之外，请登录后立即修改密码。

### 构建

Windows 请在 Git Bash 中执行，`build.sh` 会自动转交 WSL 构建，以保留 fnOS 生命周期脚本的 Unix 执行权限：

```bash
./verify.sh
./build.sh
```

`build.sh` 会下载并校验官方 fnpack 1.2.3，产物写入 `dist/`。

当前正式产物：`dist/sakuramedia-1.1.0.fpk`。实际测试结果和 SHA-256 见 [TEST_REPORT.md](TEST_REPORT.md)。

## 目录规划

应用数据根目录：

```text
sakuramedia-data/
├── postgres/
├── image-search-index/
├── joytag/
├── logs/
├── config/
└── integration-discovery/
```

建议媒体父目录：

```text
媒体父目录/
├── av/            # 已有媒体，可不存在，不会自动创建
├── downloads/     # 不存在时创建
└── sakuramedia/   # 不存在时创建
```

如果现有 qBittorrent 使用中文或其他下载目录名，只要它位于所选媒体父目录下，发现脚本会按实际 Mount 自动映射。例如：

```text
qB: /downloads -> 宿主机 /vol2/用户目录/影视/下载
SakuraMedia: /vol2/用户目录/影视 -> /mnt/media1
结果: /downloads -> /mnt/media1/下载
```

## 自动发现结果

### 已经自动完成

- 容器、镜像、端口、Mount、Network、Compose Labels 和健康状态收集。
- qBittorrent 保存路径到 SakuraMedia 本地路径的映射。
- Jackett API Key只读提取和 Torznab URL生成。
- 通过运行中 Jackett 的 torznab `t=indexers` 接口获取已配置 Indexer 的权威名称与 PT/BT 类型。
- 唯一且完整的候选实例自动选择。
- 经 SakuraMedia probe API通过的下载器和 Indexer 幂等写入；新增 Indexer 按上游相同查询形态并发探测，仅导入健康站点，避免任一坏站导致上游搜索整体失败。

### 自动发现后需要确认

- 同时发现多个 qBittorrent 或 Jackett。
- Jackett 接口不可用且回退配置文件时，无法确定 PT/BT 的 Indexer。
- 下载目录不在媒体父目录内、跨文件系统或只读。
- 外部服务未发布端口且存在多个可复用网络。

候选文件位于：

```text
sakuramedia-data/integration-discovery/
├── qbittorrent-candidates.json
├── jackett-candidates.json
└── discovery-report.json
```

在 fnOS 配置向导中填写候选 ID，再选择“重新检测，仅补充缺失配置”。

### 必须由用户填写

- qBittorrent 仅保存 PBKDF2 等不可逆密码哈希时的明文密码。
- Jackett 配置目录不可读且无法取得 API Key。
- Docker Inspect 无法可靠推导的手动地址或路径。

本项目不会破解密码、重置密码或修改外部服务配置。

## 配置优先级

```text
fnOS 向导明确填写
  > SakuraMedia 中已有且验证过的配置
  > 自动发现并验证成功的配置
  > 默认值
```

普通重新检测不会覆盖已有配置。只有明确选择“重新检测并更新”才会更新，并在写入前备份原 API 配置。

## 升级和卸载

- 升级保留 PostgreSQL、媒体库、发现结果和集成配置。
- 升级前备份 Compose 环境、FPK 配置、初始化状态和可用状态下的 PostgreSQL dump。
- 默认卸载只删除程序，保留全部数据。
- 可分别删除缓存/日志/模型、PostgreSQL、集成配置。
- 删除前验证应用 marker；任何选项都不会删除媒体父目录中的影片。

## 状态与日志

```bash
appcenter-cli status sakuramedia
docker compose -f /var/apps/sakuramedia/target/docker/docker-compose.yaml ps
docker logs --tail=200 sakuramedia
```

关键日志：

```text
sakuramedia-data/logs/bootstrap.log
sakuramedia-data/integration-discovery/bootstrap-report.json
```

日志和普通报告不会出现完整密码、API Key 或数据库连接密码。

## 当前限制

- 首版完整模式只提供跨架构 CPU JoyTag，不包含 OpenVINO/CUDA。
- 自动集成面向 Jackett 聚合器；v0.4.17 起上游索引器逐站配置 Torznab 地址与 API Key，本包导入时统一使用所发现 Jackett 实例的 Key，手动接入 Prowlarr 或原生 Torznab 站点请在应用设置里自行添加。
- fnOS 原生 wizard 是静态 JSON，多实例通过候选 ID确认，不能动态生成下拉列表；因此集成高级字段放在安装后的“配置”向导。
- 未发布 WebUI 端口且不能通过可靠 external network 访问的外部服务需要手动调整。
- 上游 Web 登录页无法从 fnOS 桌面入口自动得知 NAS 的 API 端口，首次登录需填写 `http://NAS_IP:API_PORT`。

## 更多文档

- [安装与配置](docs/INSTALL.md)
- [自动发现机制](docs/DISCOVERY.md)
- [升级与卸载](docs/UPGRADE-UNINSTALL.md)
- [故障排查](docs/TROUBLESHOOTING.md)
- [项目目录树](docs/PROJECT-TREE.md)
- [测试报告](TEST_REPORT.md)

## 许可证

本项目使用 GPL-3.0。SakuraMedia、SakuraMediaBE 及第三方镜像仍遵循各自许可证。
