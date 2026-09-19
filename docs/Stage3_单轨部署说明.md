# Alembic 单轨启动与部署

本文件描述待验收的 Stage 3 代码行为。生产仍为 3e3303f，本阶段不自动部署。

## 开发与测试

本地 backend 安装依赖、配置 backend/.env 后，先 `alembic upgrade head`，再启动 uvicorn。应用在所有环境中只做 revision guard，不调用 create_all。

普通 API 单元测试的 conftest 仍建立并清理独立临时 SQLite 数据库，其 client fixture 显式替换 revision guard。测试生命周期与生产生命周期分离。专用 revision/lifespan 测试使用真实 Alembic 或明确构造的反例，不替换生产 guard。

## 部署入口

首次部署使用 `bash scripts/deploy_production.sh`，后续使用 `bash scripts/update_production.sh`。需要已安装 Git、Docker Compose、Python 3，以及配置好的根目录 `.env`。

可设置 `EXPECTED_COMMIT` 为完整审核 hash，部署会核验拉取后的 HEAD。只允许 fast-forward。工作区必须干净，唯一例外是既有 backup_mysql.sh 的零内容差异权限状态。任何未知改动阻止部署。

两个入口在拉取后重新加载 `scripts/production_release.sh`，共用以下流程：

```text
确认 Git commit / Compose config / runtime storage
 -> 构建 backend 与 web
 -> MySQL/Redis health ready
 -> 新镜像 alembic current（未知 revision 失败）
 -> 标准数据库备份成功
 -> 停止旧 worker/beat 与 backend，进入维护窗口
 -> 再检查 runtime storage
 -> 独立 compose run backend alembic upgrade head
 -> revision guard + drift（含未知 WARNING 检查）
 -> 启动 backend 并等待 health
 -> 按配置启动 worker/beat
 -> Web、health、最终 revision 与 drift 校验
```

后台任务默认 `ENABLE_BACKGROUND=auto`，保留原来启用状态；`1` 启用 worker/beat，`0` 保持关闭。当前低配生产未启用 background profile。三个服务使用同一个 BACKEND_IMAGE，worker/beat 自身也注册只读 revision guard。

Compose depends_on/healthcheck 只负责服务可用性；显式部署脚本才负责迁移顺序。直接手动 compose up 不会自动迁移，数据库 revision 不匹配会使 API/Celery 启动失败。

## 失败行为

- Git、构建、数据库可用性、current 或备份失败：停止，不启动新应用。
- migration/revision/drift 失败：停止，旧应用已停写，新应用不启动；人工确认后恢复。
- health 或最终校验失败：返回非零，不宣告成功；不自动 rollback/downgrade/stamp。
- 没有 entrypoint migration、自动修复、自动 adoption、drop/recreate。
- 日志写入 `/var/log/ai-study-deploy/<UTC-time>-<pid>`，目录/文件权限受 umask 077 限制；终端只报告步骤、commit 与日志位置，不打印原始连接错误或密码。

默认调用现有 `scripts/backup_mysql.sh`。它目前固定 `/opt/ai-study`、每日文件名；本轮未改动该生产脚本。非标准 APP_DIR 必须通过 BACKUP_SCRIPT 指定已经审核、能备份对应数据库的脚本。备份工具的非零退出会阻断后续步骤。

## Revision Guard

`python -m app.core.revision_guard` 读取实际迁移图，要求单 base、单线、单 head，并读取 alembic_version，要求唯一版本且等于代码 head。Guard 只读，不能替代 Drift Checker 对完整结构的验证。

API lifespan 在管理员初始化之前检查；Celery worker_init/beat_init 失败时以 SystemExit 中止，避免普通信号异常被 Celery 吞掉后继续运行。

## CI

`.github/workflows/schema.yml` 在 main push 与 PR 上使用独立 MySQL 8.4 服务。运行真实空库全链、alembic check、Drift、目标 revision no-op 与禁用 create_all 的启动验证，然后运行 pytest、当轮 ruff、shell syntax 和 Compose config。

`backend/tests/verify_schema_runtime.py` 只接受显式 SCHEMA_TEST_DATABASE_URL，数据库名必须以 stage3_test 开头且完全为空。禁止将它连接生产。测试运行后数据库由隔离 CI/测试环境销毁，脚本不会清空已有库。

## 上传数据保护

本轮不增加 volume。部署前和旧进程停止后检查 backend/worker 的 uploads/vector_db：若存在未被持久化挂载覆盖的文件或软链接，拒绝替换容器，要求先完成独立存储迁移。检查使用只读 tar 流，不显示文件名/内容，不复制或删除业务文件。

## 正式切换与回退

正式部署前确认：目标 commit 已审核并推送、依赖构建方案已批准、当前 revision=20260909_001、Drift=0、有效备份可用、上传数据迁移或零文件检查通过。

本轮无新 revision，因此现生产 upgrade 预期 no-op。记录部署前后结构指纹；成功后核验 API health、公开 health/Web、登录/知识点鉴权入口、后台任务（如启用）以及日志。

如果仅本轮代码切换失败且 revision/结构未变化，可人工选择已保存的 3e3303f 镜像恢复服务；该旧版本仍有 create_all，属于临时恢复双轨，需要记录并重新安排切换。如果任何真实 migration 已执行，不自动回退数据库或旧代码，先判断兼容性。还原备份只在独立审核的恢复操作中执行。
