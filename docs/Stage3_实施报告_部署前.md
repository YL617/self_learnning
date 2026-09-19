# Stage 3 实施报告（部署前）

日期：2026-09-12。基线：3e3303ff7fffc0c8cbc2945f4f3efd69eb7fabdf。

结论：Stage 3 代码与部署前验证已完成，等待验收；未 commit、未 push、未执行生产 Cutover，未进入 Phase 2。

工作区：`C:/Users/杨乐/.codex/worktrees/ai-study-stage3`，分支 `codex/stage-3-single-track`。原项目工作区的未提交文件未覆盖。

## 1. 先审计后修改

审计记录见 [启动路径审计](./Stage3_启动路径审计.md)。原实现由 lifespan 无条件 create_all，两个部署脚本先启动应用再 migration，Celery 无 revision guard，Compose 无 readiness healthcheck，未接入 Schema CI。

本轮最终链路为：数据库可用 -> 显式 Alembic migration -> revision/drift 通过 -> API 健康 -> 可选 worker/beat -> Web 与最终核验。

## 2. create_all 移除位置

`backend/app/main.py` 移除 lifespan 中的 Base.metadata.create_all 及 Base 导入，替换为只读 require_schema_revision。backend/app 中不再存在 create_all 调用。

pytest conftest 保留临时 SQLite 的 drop_all/create_all；其 client fixture 显式替换 guard，专用生产生命周期测试不使用该替换。没有要求所有业务单元测试经 Alembic 建库。

## 3. 开发数据库初始化

README 与部署指南更新为：配置 backend/.env -> `alembic upgrade head` -> uvicorn。开发和生产应用均不自动建表。

README 的 Compose 开发示例先启动数据库并运行独立 migration，再启动应用。生产使用带备份与失败门槛的部署入口，不能直接套用开发示例。

## 4. deploy/update 新流程

两个入口采用 ff-only，拒绝未知工作区修改；只保留既有 backup_mysql.sh 零内容差异权限状态的例外。拉取后重新加载共用 production_release.sh，支持 EXPECTED_COMMIT 核验。

共用流程：构建 backend/web -> MySQL/Redis 可用 -> 新镜像 alembic current -> 标准备份成功 -> 停止旧后台任务与 API -> 再次 runtime storage 检查 -> 独立 compose run migration -> revision guard/drift -> API 启动健康 -> 后台任务 -> Web -> 最终 health/revision/drift。

首次部署入口现在要求系统已安装 Docker/Git/Python 3；不再把系统包安装、防火墙变更与应用发布混在一次脚本运行。首次缺少 .env 时复制示例后退出，要求配置完成再运行。

## 5. Migration failure 行为

- set -euo pipefail，每一步非零均停止。
- 备份失败不会执行 migration；migration、revision 或 drift 失败不会启动新应用。
- 迁移前停写后若失败，保持维护状态，等待人工处理，不自动启动旧版本。
- 无自动 stamp、downgrade、drop/recreate、create_all、隐式 entrypoint migration。
- 原始命令日志受 umask 077 保护，终端仅输出步骤状态、commit、镜像标签及受限日志路径，不打印凭据或原始连接异常。

## 6. Worker/beat

backend、worker、beat 指向同一 BACKEND_IMAGE。Compose 的后台任务依赖健康 API/MySQL/Redis；显式部署流程在迁移成功且 API 健康之后才启动后台任务。

ENABLE_BACKGROUND 默认 auto，保留现有运行状态；1 显式启用，0 关闭。生产当前 background 未启用，本轮没有启动它。

增加 worker ping 与 beat revision 校验；worker_init/beat_init 均注册只读 guard，版本不符以 SystemExit 中止，避免 Celery 吞掉普通信号异常。

## 7. Revision Guard

新增 backend/app/core/revision_guard.py。动态读取代码迁移图，要求单 base、单线、单 head；数据库必须有且只有一个 alembic_version，且等于代码 head。

空库、落后版本、超前版本、未知版本、多 revision、迁移图异常、数据库连接失败均拒绝启动。Guard 只检查 revision，不代替完整 drift 检查，不写数据库。

API 在管理员初始化之前检查；开发环境同样检查。测试验证 guard SQL 为只读，连接异常对外脱敏。

## 8. Drift CI

新增 .github/workflows/schema.yml，在 main push 与 PR 运行 MySQL 8.4 服务、Fresh 全链、alembic check、Drift、生产式启动、pytest、当轮 ruff、Bash syntax 和 Compose config。

DriftResult 明确将未知 WARNING 作为非零退出；未修改既有字段白名单或方言归一化规则。CI 要求 0 ERROR / 0 Unknown WARNING。

新增 tests/verify_schema_runtime.py，仅接受显式命名 stage3_test... 的真正空 MySQL 测试库；拒绝非空库。实际 GitHub Actions 尚未运行，因为本轮未提交推送。相同核心数据库检查已在隔离 MySQL 中执行；YAML/触发器/Compose 配置已校验。

## 9. Fresh MySQL 权威验证

使用 MySQL 8.4.11 独立容器、内部隔离网络、独立匿名数据卷。未连接生产数据库，未使用生产账户或用户数据。设置测试容器 CPU/内存限制。

从经断言无表的 stage3_test_fresh 执行真实 Alembic upgrade head，16 个 revision 全链通过，32 张业务表及 alembic_version 完整。

- current/head：20260909_001。
- Drift：0 ERROR，42 WARNING，0 Unknown WARNING。
- WARNING：40 个既有字段默认值白名单，2 个已证明来源的 FK 自动索引。
- alembic check：No new upgrade operations detected。

没有更改任何历史 migration、revision 链或 ORM 字段。

## 10. Production-like 验证

在以上隔离 MySQL 已达到目标 revision 后，再运行 upgrade head，并启动新版 API。

这一验证模拟“目标 revision + 完整目标 Schema”的现有数据库，不是导入真实生产业务数据的克隆；Fresh 默认值与生产历史默认值的已批准差异仍由既有 Drift 规则处理。

- no-op 升级通过。
- 全局 SQLAlchemy 执行钩子拒绝非 SELECT/SHOW/DESCRIBE/SET SQL。
- 将 Base.metadata.create_all 替换为直接失败的函数，应用 lifespan 仍启动成功。
- TestClient health=200，Inspector=ADOPTION COMPLETE AT 20260909_001。
- 结构指纹前后完全一致：`155944e9a6a0660366beb0e78dc3ba938dc7aa3bf1719be1b171273e712f6a7e`。
- 另以真实 Uvicorn 进程启动隔离 API，HTTP /health=200。

此指纹算法包含测试库中所有表的列、PK、FK、index、unique，包含 alembic_version；它用于本轮前后比较，与 Stage 2.10 的生产指纹算法不相同，不应跨算法比较。

隔离 API/MySQL 容器、专用网络、匿名数据卷与远程测试目录已清理。

## 11. Pytest 与 SQLite

| 验证 | 结果 |
| --- | --- |
| 修改前全量基线 | 133 passed |
| Revision/lifespan/后台保护新增测试 | 11 passed |
| 部署流程、失败分支与存储边界测试 | 15 passed |
| 修改后 full pytest | 159 passed |
| 最后补充后台/Web 健康命令后的部署专项复验 | 15 passed |
| Fresh SQLite 全链与历史升级回归 | 通过，0 ERROR / 40 白名单 WARNING |
| Adoption / Cleanup 既有回归 | 全量测试中通过 |

测试基线无失败；本轮无未解决测试失败。测试中曾修正 Git Bash 对 PATH 的处理，确保模拟命令实际被调用，失败分支测试同时检查对应失败步骤已执行，避免假通过。

pytest 仅有既有 Starlette/httpx 弃用提示。部署编排的异常路径使用可控的模拟 Docker/Git/备份命令验证；真实 MySQL 迁移、真实 Uvicorn 启动独立验证。未把模拟部署称为已在生产执行。

## 12. Ruff / Docker / Shell

- 本轮 Python 文件 ruff 全通过。
- backend 全库仍有 10 个历史 I001，未扩大修复。
- 三个发布 shell 文件 Bash syntax 通过；部署健康命令补充后专项复验包含 syntax。
- 隔离目录执行 docker compose --profile background config --quiet 通过。
- 解析 Compose 确认三个 Python 服务共享 image、APP_ENV=prod、健康依赖正确。
- Workflow YAML 与触发器检查通过；git diff --check 通过。

## 13. 可重复构建审计

详见 [依赖与存储方案](./Stage3_依赖与存储方案.md)。没有 Python lock，requirements 使用下限范围、基础镜像 tag 浮动；同 commit 默认 rebuild 仍可能升级包。

本轮未更改 requirements、Dockerfile 或包版本；隔离验证复用现有运行镜像依赖。只新增 backend/.dockerignore 防止构建上下文带入 .env、虚拟环境和运行时数据。

建议生产 Cutover 前批准当前依赖冻结与基础镜像 digest 方案，并完成候选镜像验证；或者明确批准复用既有依赖组装候选镜像。不能把当前未锁版本的默认 build 当成可重复构建。

## 14. uploads/vector_db 风险

生产审计 Mounts=[]，两个目录目前共 0 文件；未来文件在容器重建时可能丢失。本轮没有创建/修改生产挂载或复制生产业务文件。

新增只读 storage preflight：发现未持久化的文件/链接，或检查失败，就拒绝替换容器。正式迁至命名卷/共享卷、备份与权限校验建议作为独立 Stage 3.x，具体方案已记录。

## 15. Diff 摘要

修改：README.md、backend/app/main.py、backend/app/tasks/celery_app.py、backend/app/core/schema_drift.py、backend/tests/conftest.py、docker-compose.yml、scripts/deploy_production.sh、scripts/update_production.sh、docs/DEPLOYMENT_GUIDE.md。

新增：backend/app/core/revision_guard.py、backend/.dockerignore、backend/tests/test_revision_guard.py、backend/tests/test_deployment_flow.py、backend/tests/verify_schema_runtime.py、scripts/production_release.sh、scripts/check_runtime_storage.py、.github/workflows/schema.yml，以及本轮审计/部署/依赖存储/实施报告四份文档。

无业务功能、知识点 Phase 2、数据库模型或 migration 变更。原工作区未跟踪 docs/ECS...、web/ui-*.png 等未纳入本轮。

## 16. Commit 规划

1. `refactor: 生产数据库切换为 Alembic 单轨管理`：main、revision guard、Celery guard、fixture、guard 测试、只读保护的未知 WARNING 失败语义与开发初始化说明。
2. `ops: 调整生产部署为 migration-first 流程`：部署公共流程与两个入口、Compose health/共享镜像、存储 preflight、部署失败测试、backend/.dockerignore、部署和风险文档。
3. `ci: 增加 Alembic Schema Drift 检查`：Workflow 与隔离 MySQL runtime 验证脚本、实施报告。

本轮仅准备规划与工作区 Diff，尚未生成这些提交或推送，避免在部署验收前混淆生产版本。

## 17. 生产部署方案

验收本报告后，先确定依赖冻结或候选镜像复用方式，再按上述规划提交、推送、复核候选镜像内容和依赖。

生产 Cutover 单独批准后：只读核验 3e3303f / 20260909_001 与 Drift -> 标准备份与存储检查 -> 审核 commit 快进同步 -> 显式 migration-first 发布 -> revision/head 与结构指纹 -> API/public health/Web/后台任务按启用状态验收。

本轮未新增 revision，当前生产 migration 预期必须为 no-op；如出现任何待执行 DDL 或非预期 drift，停止并报告。

## 18. Rollback 与最终生产状态

部署前保存旧镜像 ID、配置和有效备份。若仅本轮代码切换失败，且 revision/结构指纹未变化，可以人工恢复 3e3303f 镜像；这会暂时恢复旧 create_all 双轨行为，必须记录并重新安排切换。不要自动执行 downgrade 或 stamp。

若后续真实 migration 已改变结构，回退旧代码前先评估兼容性；数据库恢复属于单独审核操作，不能自动覆盖生产。

最终只读确认生产仍为：

```text
server HEAD = 3e3303ff7fffc0c8cbc2945f4f3efd69eb7fabdf
alembic current = 20260909_001 (head)
backend / Web / MySQL / Redis 原容器持续运行
git status = 原有 scripts/backup_mysql.sh 权限状态
```

Stage 3 的生产代码切换尚未发生。当前状态为：**部署前实现与隔离验证完成，等待生产 Cutover 确认**。
