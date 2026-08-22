# 测试报告

更新时间：2026-08-22

正式产物：`dist/sakuramedia-1.1.0.fpk`

SHA-256：`75220e82767a6d3a41d86ca4f3128a649c91db2ed297c3284b1ffc852362e984`

## 本地自动化测试

已执行：

```bash
./verify.sh
./build.sh
```

结果：

- 32 项 Python 单元测试通过。在 1.0.3 的 30 项基础上新增：旧版空 Key 站点按当前 Jackett 候选回填、索引器名称去重。
- 全部 Shell 脚本通过 `bash -n`；WSL 环境 ShellCheck 通过（动态 `source` 的 SC1091 按项目规则排除）。
- manifest、wizard、resource、privilege 和 UI JSON 解析通过。
- 轻量/完整两套 `docker compose config` 通过。
- FPK 外层必需文件、`app.tgz` 内容和 `cmd/*` 执行权限检查通过；`__pycache__` 未进入产物（24 个外层成员、20 个 `app.tgz` 成员）。

## 1.1.0 变更内容

1. 同步官方后端 `v0.4.21`（`sha256:3977291e9531...`）、前端 `v0.4.13`（`sha256:22bd7b3a831e...`），均为 Docker Hub 官方多架构 manifest（amd64/arm64）。
2. 适配 v0.4.17+ 索引器配置重构（整表替换 + 逐站 Torznab 地址与 API Key）：bootstrap 现有条目原样回传保留用户配置；服务端名称唯一性校验通过合并去重满足；空 Key 且仍由当前 Jackett 提供的站点自动补齐。
3. 新增 FnDepot 第三方应用源接入（GitHub Actions 构建 + Release + `fnpack.json` V2 格式经 GitHub Pages 分发，platform=all 单包）。

## fnOS 实机测试（1.1.0，2026-08-22）

- `install-local` 保留数据重装 1.1.0 成功；新镜像 `sakuramediabe:v0.4.21`、`sakuramedia-web:v0.4.13` 实际运行，PostgreSQL healthy。
- 固定账号 `yiwan/yiwan123` 登录 201；媒体库 ID 1、下载器 ID 1、PostgreSQL 数据全部保留。
- 后端 v0.4.21 自身完成了旧索引器数据迁移：97 个站点逐站携带 API Key，无需人工重配。
- FPK config 生命周期在新版 API 上正常：下载器 kept；索引器 updated（97 个，18 个坏站再次被健康探测过滤，自愈重试按设计工作）；`connection_healthy: true`。
- 端到端搜索：`GET /download-candidates?movie_number=SSNI-888&indexer_kind=bt` 返回 200 和 36 个候选，耗时 0.30 秒；Web HTTP 200。

1.0.3 及更早版本的实机验证结论（Jackett 类型判定修复、导入前健康探测、启停循环、install-local 流程细节等）见 git 历史中对应版本的测试报告。

## 尚未验证

- fnOS Web 应用中心"手动安装正式 FPK"仍被该账号的 OTP 二次验证阻塞；CLI `install-fpk` 对已安装应用不执行升级，因此原生 `upgrade_init/upgrade_callback` 路径及 PostgreSQL dump 回滚仍未被真实触发。
- NAS 整机重启恢复测试未执行；按约定该操作需再次确认后才能进行（会影响 NAS 上其他正在运行的服务）。
- ARM64 fnOS 真机未测试（FPK 通用，镜像多架构已确认存在）。
- FnDepot 客户端实机添加源并安装的端到端流程待 Release/Pages 发布后由用户在 FnDepot 中验证。


