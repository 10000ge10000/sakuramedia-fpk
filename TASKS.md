# 任务清单

- [x] 研究 SakuraMedia 前后端与 fnOS 官方 FPK 规范。
- [x] 创建 FPK 骨架、向导、Compose 和生命周期入口。
- [x] 实现 qBittorrent/Jackett 自动发现与路径映射。
- [x] 实现 SakuraMedia HTTP API 幂等初始化。
- [x] 编写模拟 Docker Inspect 的自动化测试。
- [x] 完成本地静态验证并修复问题。
- [x] 使用 fnpack 1.2.3 构建正式 FPK。
- [x] 在授权 fnOS 测试机完成轻量/完整模式、启停、发现和临时 qB 全链路验收。
- [x] 整理最终测试报告与未验证项。
- [x] 将首次安装向导精简为两步，集成参数改为安装后按需配置。
- [x] 同步官方前端 v0.4.2、后端 v0.4.4 及多架构镜像 digest。
- [x] 固定新安装账号 yiwan/yiwan123，并为旧安装提供一次性账号迁移。

受外部条件阻塞的项目见 `TEST_REPORT.md`：Web 手动安装需要 OTP，NAS 重启需要再次确认，原生升级回调未被当前 CLI 触发。
