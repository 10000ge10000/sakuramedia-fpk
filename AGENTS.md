# AGENTS.md

## 项目说明

本项目将 SakuraMedia 前后端封装为可由飞牛 fnOS 应用中心管理的 Docker FPK。

## 技术栈

- fnOS FPK / fnpack 1.2.3
- Bash 生命周期脚本
- Python 3.12 标准库
- Docker Compose

## 常用命令

```bash
./verify.sh
./build.sh
```

## 目录约定

- `app/docker/`：Compose 和运行时脚本。
- `cmd/`：fnOS 生命周期入口。
- `wizard/`：安装、配置、升级和卸载向导。
- `tests/`：模拟 Docker Inspect 的自动化测试。

## 修改规则

- 不改变 Compose 服务名 `postgres`、`sakuramedia`、`sakuramedia-web`、`joytag-infer`、`qdrant`。
- 不把密码、API Key、Token 或真实 NAS 配置写入仓库。
- 不在业务容器挂载 Docker Socket，不修改外部 qBittorrent/Jackett。
- 新镜像版本必须同步更新 digest、README、CHANGELOG 和验证断言。
- 首次安装向导保持单步“快速安装”；新安装账号由生命周期脚本固定设置，集成凭据和多实例选择只放在安装后的配置向导。

## 验证方式

修改后运行 `./verify.sh`；发布前运行 `./build.sh` 并在 fnOS 测试机手动安装生成的 FPK。
