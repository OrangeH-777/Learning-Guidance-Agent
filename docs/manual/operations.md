# 本地运行、备份与恢复

本文对应已实现的单进程本地开发环境，不替代尚未确认的服务器/HTTPS/容器部署方案。安装与启动见根目录 README。

## 进程与就绪

后端一个 Uvicorn worker。调度器启动取得 PostgreSQL会话锁；第二个同库进程不能同时调度。锁连接丢失后停止受理，需要在数据库恢复后重启后端。重启时非终态标 INTERRUPTED，无断点续跑承诺。

`/health` 检查进程；`/health/ready` 检查数据库、扩展与调度器。`python -m scripts.check_database` 是只读数据库检查；`alembic check` 检查模型与迁移差异。模型/嵌入及课程可用性需另行检查。

## 本地数据库

已验证 PostgreSQL17.11、pgvector0.8.6。容器 `lga-postgres-dev`，端口仅127.0.0.1:55432，volume `lga-postgres-data`。开发库 lga_dev，测试库 lga_test，恢复演练库 lga_restore_test。测试角色 lga 具有扩展/建库权限，仅用于本地开发；正式部署需另设受限运行账户。

禁止让 TEST_DATABASE_URL 指向开发库或真实数据。集成测试、浏览器测试和迁移检查均会清空测试库，不能并行运行。

## 备份与恢复

数据库备份须包含表、向量、版本关系和 Alembic 状态；另行安全备份加密主密钥及旧密钥、配置、代码/锁文件、课程原始文件。仅有数据库密文而没有相应Fernet密钥时无法恢复个人模型调用。

本地演练命令（目标恢复库必须是新建专用库，不覆盖原库）：

```powershell
docker exec lga-postgres-dev pg_dump -U lga -d lga_dev -Fc -f /tmp/lga-dev.dump
docker cp lga-postgres-dev:/tmp/lga-dev.dump tests/results/lga-dev.dump
docker exec lga-postgres-dev createdb -U lga NEW_RESTORE_DATABASE
docker exec lga-postgres-dev pg_restore -U lga --exit-on-error --no-owner -d NEW_RESTORE_DATABASE /tmp/lga-dev.dump
```

2026-09-27已实际恢复到 lga_restore_test，确认迁移版本308aa7fa06a9、1个课程目录及pgvector0.8.6。该备份是当前开发库的目录级数据，不声称已经演练大量用户资源恢复。

恢复后先在隔离端口连接恢复库，核对表数、用户/资源数量、来源可追溯性、密钥解密、索引版本及非终态处理，再讨论切换。不要直接将新版本数据库交给旧代码。出现迁移失败时保留原库/备份，先在独立恢复库验证。

## 迁移回退限制

初始迁移建立业务表和vector；第二迁移将来源唯一约束调整为公共/私有各自的版本约束。第二迁移的降级会恢复旧的course/source/content_hash唯一约束；如果已有同内容多版本数据，旧约束不能容纳，降级应失败并回滚，不能删数据强行通过。

已在独立测试库验证空库升级、版本升级、空数据回退及再次升级。带业务数据的发布回退以验证过的备份恢复为主；不要直接运行 `alembic downgrade base`，它会删除业务表。

## Fernet密钥轮换

停止新任务受理并保留数据库备份；生成新的Fernet密钥放入 MODEL_CREDENTIAL_ENCRYPTION_KEY，将仍需解密的旧密钥放入 MODEL_CREDENTIAL_PREVIOUS_KEYS（JSON列表）。随后执行：

```powershell
uv run --locked python -m scripts.rotate_credentials
```

脚本在单事务内重加密全部非空模型密文，失败整体回滚，不打印任何密钥。核对模型连通和备份兼容后再移除在线旧密钥；历史备份仍需要旧密钥，保留方式由实际安全存储方案决定。只修改 `.env` 而丢弃旧密钥不能解密已有配置。

## 日志与保留期

服务错误只记录代码、任务ID等必要信息，不输出模型响应正文、密码、密钥、完整画像或数据库连接串。测试报告与备份属于忽略的运行产物，发布前只归档脱敏摘要。

会话按到期时间校验；当前尚无自动清理画像、对话、历史资源或旧模型密文的周期。正式数据保留、用户删除语义、费用预算、访问日志保留、备份存放位置、HTTPS和进程管理必须在S10评审，未将未经确认的期限写成现行政策。
