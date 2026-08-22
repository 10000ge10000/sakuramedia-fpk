# fnOS 安装与配置

## 前置条件

- fnOS 已安装并运行 Docker。
- 支持 x86_64 或 ARM64。
- 轻量模式建议至少 2 GiB 内存；完整模式最低 4 GiB，建议 4 核 8 GiB。
- 媒体父目录已经存在，并且应用用户具备读写权限。

## 快速安装向导

向导现在只有一步“快速安装”：

- 主动选择轻量/完整模式。
- 填写媒体父目录。
- 自定义数据目录可留空，留空使用 `$TRIM_PKGVAR/sakuramedia-data`。
- 确认 API/Web 端口。
- 不再填写账号，安装完成后固定使用用户名 `yiwan`、密码 `yiwan123`。

PUID/PGID 固定使用默认 `1000`，时区使用 `Asia/Shanghai`。qBittorrent/Jackett 自动发现始终在安装回调中执行，不再要求用户先填写开关或手动连接信息。

已有安装升级时保留已有账号凭据，只有新安装使用固定账号。固定密码较弱，建议在可信网络中使用并尽快修改。

自定义数据目录必须是绝对路径，不能是 `/` 或存储卷根目录。媒体父目录在容器内固定为 `/mnt/media1`。API/Web 端口必须不同且未被占用。SakuraMedia 密码至少 8 位，不会进入普通日志。

## 安装后配置

安装完成后打开 fnOS“配置”向导，仅在以下情况使用：

- 自动发现了多个 qBittorrent/Jackett，需要选择候选 ID。
- qBittorrent 只有不可逆哈希密码，需要补充明文密码。
- 外部服务没有可安全读取的 API Key 或地址。
- 需要切换完整/轻量模式或修改端口、媒体路径。

## 安装成功判断

```bash
appcenter-cli status sakuramedia
docker ps --filter name=sakuramedia
curl -I http://127.0.0.1:38080/
```

轻量模式只应存在三个运行容器；完整模式额外存在 `joytag-infer` 和 `qdrant`。
