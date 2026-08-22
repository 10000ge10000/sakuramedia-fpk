# qBittorrent 与 Jackett 自动发现

## 识别依据

发现脚本读取 `docker ps -aq` 和 `docker inspect`，分析名称、镜像、Labels、环境变量、Published/Exposed Ports、Mounts、Networks、Compose Project/Service 和健康状态。

只读取 Docker 明确挂载的配置目录和 Compose Labels 指向的上下文，不扫描整台 NAS。

## qBittorrent

已覆盖 linuxserver、hotio、superng6、qbittorrent-nox、飞牛应用中心和自定义命名场景。

密码优先级：明文环境变量 > 手动向导。配置文件中的 PBKDF2 哈希只用于判断“已设置密码”，不会尝试破解或重置。

路径映射使用最长容器 Mount 前缀。只有宿主机路径位于媒体父目录下且挂载可写时，才允许进入 SakuraMedia 的 storage-test。

## Jackett

Indexer 目录与 PT/BT 类型的获取顺序：

1. 使用已提取的 API Key 请求本地 Jackett 的 torznab `t=indexers` 接口（`/api/v2.0/indexers/all/results/torznab/api`）。该接口与 Torznab 同源认证，不依赖 Jackett 管理端会话；只取 `configured=true` 条目，`public` 映射为 BT，`private`/`semi-private` 映射为 PT。
2. 接口不可达、Key 无效或返回异常时，从挂载配置中的 `ServerConfig.json` 和 `Indexers/*.json` 只读回退；此时列表型配置里的 `type` 是控件类型，绝大多数条目将标记为需要人工确认。

每个 Indexer 都使用实际 ID 生成 Torznab URL。无法确定 PT/BT 类型的条目不会猜测导入，会列入报告的 `jackett_indexers_missing_kind`。候选中的 `indexer_source` 字段标记本次数据来源（`torznab-api` 或 `config-files`）。

请求 URL 中包含的 API Key 只存在于进程内存和秘密文件，不会写入任何候选 JSON 或报告。

## 安全

候选 JSON 不包含完整密码或 API Key。秘密保存在 `config/fpk-secrets.json`，权限为 `600`。任何发现过程都不会修改外部容器、网络或配置文件。
