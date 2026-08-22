# 故障排查

## 安装提示 Docker 未运行

```bash
docker version
docker compose version
docker info
```

确保 fnOS 应用中心中的 Docker 已启动。

## 模型下载失败

检查 NAS 是否能访问 GitHub Release：

```bash
curl -I https://github.com/tinypinglite/sakuramediabe/releases/download/model/model_vit_768.onnx
```

重新打开配置向导并选择完整模式会再次校验和下载；损坏的临时文件不会被保留。

## qBittorrent 只发现地址但没有自动保存

查看 `qbittorrent-candidates.json` 的 `password_state`。若为 `hash-only`，在配置向导补充明文密码；项目不会破解 PBKDF2 哈希。

## 目录映射失败

确认 qBittorrent 的实际保存路径位于所选媒体父目录下：

```bash
docker inspect <qB容器名> --format '{{json .Mounts}}'
```

跨盘无法硬链接，映射到媒体父目录之外的路径不会自动写入。

## Jackett Indexer 没有全部导入

查看 `bootstrap-state.json` 的 `skipped_unhealthy` 列表：这些站点在导入前探测未通过（需要 FlareSolverr、站点失效或超时）。上游搜索对任一失败 Indexer 会整体中断，因此它们被有意排除；站点恢复后在配置向导重新检测即可自动补回。若大量公共站点需要 Cloudflare 挑战，可在 Jackett 侧配置 FlareSolverr 后重新检测。

Jackett 类型判定优先走 torznab `t=indexers` 接口；接口不可用回退配置文件时，列表型配置无法得出 PT/BT 的条目会记入 `skipped_unknown_kind`，需要人工确认。

## 应用状态异常

```bash
appcenter-cli status sakuramedia
docker inspect sakuramedia-postgres sakuramedia sakuramedia-web
docker logs --tail=200 sakuramedia
```

完整模式还要检查 `joytag-infer` 和 `qdrant`。
