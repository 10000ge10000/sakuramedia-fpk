# 更新日志

## 1.1.0 - 2026-08-22

- 同步官方后端 `v0.4.21`、前端 `v0.4.13` 多架构镜像 digest。
- 适配 v0.4.17+ 索引器配置重构：索引器改为数据库管理、逐站 Torznab 地址与 API Key；bootstrap 导入改用整表替换语义，现有条目原样回传（保留用户手动配置与密钥），旧版升级后空 Key 且仍由当前 Jackett 提供的站点自动补齐密钥。
- 适配服务端新增的索引器名称唯一性校验，合并时自动去重名称。
- 新增 FnDepot 第三方应用源接入：GitHub Actions 自动构建发布，`fnpack.json`（V2 格式，platform=all 单包）经 GitHub Pages 分发，可在 FnDepot 源管理添加后一键安装更新。
- 新增 2 项单元测试覆盖空 Key 回填与名称去重（合计 32 项）。

## 1.0.3 - 2026-08-22

- 修复 Jackett Indexer PT/BT 类型判定缺陷：真实 Jackett 列表型配置文件中的 `type` 是控件类型而非站点隐私类型，导致全部 Indexer 被跳过、`indexer_count=0`。
- 发现优先通过运行中 Jackett 的 torznab `t=indexers` 接口获取权威名称与类型（public→bt，private/semi-private→pt），接口不可用时回退到原配置文件解析。
- 新增导入前健康探测：上游搜索对任一失败 Indexer 会整体中断，因此 bootstrap 以与上游完全相同的查询形态（`t=search&q=...&cat=6000`）并发探测新增 Indexer，仅导入应答 200 的站点；被过滤站点记录在 `skipped_unhealthy`，下次配置运行自动重试。已在库中的 Indexer 不会被自动删除。
- 发现报告新增 `jackett_indexer_sources` 与 `jackett_indexers_missing_kind`，公开候选新增 `indexer_source` 标记数据来源；bootstrap 报告新增脱敏后的 `connection_detail`。
- 请求 URL 中的 apikey 只存在于内存和秘密文件，不进入任何公开报告。
- 新增 5 项单元测试覆盖目录接口解析、降级回退、真实列表型配置不误判、探测过滤与测试错误脱敏。
- 修复 Windows Git Bash 下 `build.sh` 转交 WSL 构建时路径反斜杠被转义吞掉的问题。

## 1.0.2 - 2026-07-19

- 同步官方 SakuraMedia 前端 `v0.4.2` 和后端 `v0.4.4` 镜像及多架构 digest。
- 兼容 v0.4.4 的本地媒体库 `backend/backend_config` 结构和 Indexer 多下载器绑定 API。
- 安装向导进一步精简为单步快速安装。
- 新安装固定账号为 `yiwan` / `yiwan123`；已有安装升级保留原账号以避免登录中断。

## 1.0.1 - 2026-07-19

- 精简首次安装向导为“快速安装 + 登录密码”两步。
- 首次安装只需选择部署模式、媒体目录、可选数据目录、端口和密码。
- PUID、PGID、时区使用安全默认值；qBittorrent/Jackett 改为安装后自动发现，缺少凭据时再配置。
- 自定义数据目录改为留空即托管目录，同时兼容旧版数据目录字段。

## 1.0.0 - 2026-07-12

- 首次发布 fnOS FPK。
- 支持轻量和完整部署模式。
- 支持 qBittorrent、Jackett 自动发现和脱敏报告。
- 支持媒体库、下载器、Indexer 幂等初始化。
- 支持应用中心启停、状态、配置、升级备份和安全卸载。
