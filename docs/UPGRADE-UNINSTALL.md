# 升级与卸载

## 升级

`upgrade_init` 会在数据目录的 `config/backups/upgrade-时间戳/` 保存：

- FPK 配置和秘密文件。
- Compose `.env`。
- 自动发现与初始化报告。
- PostgreSQL 运行时可用时的 `pg_dump`。

后端镜像启动时执行上游数据库迁移。若迁移后需要回滚，先停止应用，再由管理员使用备份 SQL人工恢复；脚本不会自动覆盖数据库。

## 卸载

默认保留所有数据。删除选项只作用于带 `.sakuramedia-fnos-fpk` marker 的数据根目录：

- 运行数据：向量索引、JoyTag 模型、日志。
- PostgreSQL：数据库目录。
- 集成配置：候选报告、秘密和 bootstrap 状态。

媒体父目录、`av`、`downloads`、`sakuramedia` 中的用户影片永远不在删除范围内。
