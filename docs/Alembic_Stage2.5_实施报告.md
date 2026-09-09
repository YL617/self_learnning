# Alembic Stage 2.5 实施报告

> 任务：Legacy Cleanup 工具实现与非生产演练
> 日期：2026-09-08
> 结论：代码与非生产演练通过；尚未部署，生产 Apply 仍需人工安全门。

## 1. 新增与修改文件

### 新增

- `backend/app/core/legacy_cleanup_manifest.py`
  - 固化 `20260908_001 -> 20260909_001` 的 6 DROP + 1 CREATE；
  - 每项包含 operation、table、index、columns、unique、forward SQL、recovery SQL 和 reason。
- `backend/app/core/legacy_cleanup.py`
  - Cleanup 状态采集、严格评估、忙碌检查、备份证明校验、逐项 Apply 与恢复计划。
- `scripts/legacy_schema_cleanup_20260908.py`
  - 默认只读 CLI；显式 Apply 入口；不含 stamp 能力。
- `backend/tests/test_legacy_cleanup.py`
  - 21 项 Cleanup 单元及安全合同测试。
- `docs/Alembic_Stage2.5_实施报告.md`
  - 本报告。

### 修改

- `docs/Legacy_Production_Cleanup_Adoption_方案.md`
  - 将“仅设计”状态更新为已实现并完成非生产演练。

本阶段未新增或修改 Alembic migration，未修改 ORM model，未修改部署逻辑。

## 2. Cleanup Script

脚本：

```text
scripts/legacy_schema_cleanup_20260908.py
```

该脚本只支持已审核的 Legacy 场景：

```text
Current revision: 20260908_001
Target schema: Equivalent to 20260909_001
```

它不是通用 Schema 修复器，不接受任意 DDL、任意 revision 或任意对象清单。

### 默认 Dry Run

```bash
python scripts/legacy_schema_cleanup_20260908.py
```

只读取 Alembic revision、Schema metadata、数据库运行状态、Drift Checker 和 Adoption Inspector 结果。没有 Apply 标志时不存在 DDL 执行路径。

满足预期时退出码为 `0`，输出 6 DROP、1 CREATE、目标 revision 和计划 SHA-256 指纹；状态异常时输出 `CLEANUP BLOCKED` 并返回非零退出码。

### 显式 Apply

```bash
python scripts/legacy_schema_cleanup_20260908.py \
  --apply \
  --backup-proof /absolute/path/backup-proof.json \
  --plan-fingerprint <latest-dry-run-fingerprint>
```

只有 `--apply` 才能进入 DDL 路径。Apply 还必须提供独立备份流程生成的证明文件和最新 dry-run 指纹；脚本会重新采集数据库状态，不复用缓存的 dry-run 结果。

脚本没有 `stamp` 参数、函数或 SQL。Cleanup 与 Adoption 保持两个独立人工节点。

## 3. Cleanup Manifest

### CREATE

| 顺序 | table | index | columns | unique |
|---|---|---|---|---|
| 1 | `course_recommendations` | `ix_course_recommendations_status` | `status` | 否 |

### DROP

| 顺序 | table | index | columns | unique |
|---|---|---|---|---|
| 2 | `activation_codes` | `ix_activation_codes_id` | `id` | 否 |
| 3 | `ai_provider_snapshots` | `ix_ai_provider_snapshots_id` | `id` | 否 |
| 4 | `pet_messages` | `ix_pet_messages_id` | `id` | 否 |
| 5 | `pet_play_sessions` | `ix_pet_play_sessions_id` | `id` | 否 |
| 6 | `plan_chat_messages` | `ix_plan_chat_messages_id` | `id` | 否 |
| 7 | `plan_chat_sessions` | `ix_plan_chat_sessions_id` | `id` | 否 |

执行顺序先 CREATE 缺失业务索引，再 DROP 冗余索引。每条 DDL 使用固定常量并单独执行，不拼接用户输入。

## 4. Apply 安全门

以下检查任一失败都会阻止全部或后续 DDL：

1. dialect 必须为 MySQL；
2. `alembic_version` 必须只有一行且严格为 `20260908_001`；
3. 7 张目标表必须全部存在且均为 InnoDB；
4. 待删除索引必须名称、表、列、非唯一、BTREE、可见性和无前缀属性完全匹配；
5. 每个待删除索引对应的 `PRIMARY(id)` 必须仍存在；
6. 待删索引不得支撑 unique/constraint/FK；
7. status 索引必须确实缺失，且不得存在不同名称的等价索引；
8. Drift Checker 的 ERROR 必须恰好等于当前尚未完成的受审操作；
9. Adoption Inspector 的阻塞项必须恰好对应当前 pending 操作；
10. runtime 源码中不得出现索引 hint 或 6 个索引名硬编码依赖；
11. Apply 时数据库不得处于忙碌风险状态；
12. 备份证明、计划指纹必须通过验证。

对于中途执行后的预期部分状态，每项只能处于严格的 BEFORE 或 AFTER 定义。已经达到目标的项报告为 `ALREADY CLEAN`；同名不同列、不同唯一性或其他 drift 均不会被静默跳过。

## 5. Metadata Lock 检查

集中配置：

```text
LONG_TRANSACTION_SECONDS = 60
ACTIVE_DDL_SECONDS = 5
DDL_LOCK_WAIT_SECONDS = 30
```

Apply 前和每项操作前后检查：

- `information_schema.INNODB_TRX` 中的长事务；
- `performance_schema.metadata_locks` 中目标表的 pending metadata lock；
- `information_schema.PROCESSLIST` 中持续运行的目标表 ALTER/CREATE INDEX/DROP INDEX。

发现风险时返回：

```text
CLEANUP BLOCKED: DATABASE BUSY
```

若当前数据库账号无权完成忙碌检查，也会 fail-closed，而不是假设数据库空闲。

DDL 显式要求 `ALGORITHM=INPLACE, LOCK=NONE`。MySQL 不支持时立即停止，不自动回退到 `COPY`、`SHARED` 或 `EXCLUSIVE`。

## 6. Backup Proof

Cleanup Script 不执行备份，只验证独立备份流程产生的 JSON metadata。要求字段：

```json
{
  "backup_path": "/absolute/path/to/backup.sql",
  "size": 123,
  "sha256": "...",
  "command_exit_code": 0,
  "created_at": "2026-09-08T00:00:00+00:00",
  "revision": "20260908_001"
}
```

Apply 会重新检查文件存在、绝对路径、size > 0、实际大小、SHA-256、命令退出码、revision 和 24 小时时效。单元测试只验证 Cleanup 状态机，不伪造备份成功；完整非生产 MySQL 演练使用真实生成的 schema-only dump 及其真实校验值验证公开 Apply 入口。

## 7. Recovery Plan

Manifest 为 7 项 operation 都保存反向 SQL：

- DROP 遗留索引的 recovery 是按原名称重新 CREATE 普通索引；
- CREATE status 索引的 recovery 是 DROP 该索引。

Apply 使用单条原子 DDL、单条后验。中途失败时输出：

- 已成功操作；
- 失败操作和脱敏后的异常类型；
- 按已完成顺序逆序排列的 Recovery SQL。

异常消息正文、连接串、密码和 SQL 参数不会输出。Recovery Plan 不称为事务 rollback，因为 MySQL DDL 存在 implicit commit，7 条 DDL 无法整体事务回滚。

## 8. 自动测试结果

### Cleanup tests

```text
21 passed
```

覆盖：

- 恰好 7 项的 dry-run；
- 全部完成后的 `ALREADY CLEAN`；
- revision 错误；
- 待删索引缺失同时存在其他 drift；
- 同名索引列错误；
- 待删索引为 unique；
- PK 缺失；
- status 索引结构错误；
- 不同名称的等价 status 索引；
- 额外真实 drift；
- 非 MySQL；
- 长事务、metadata lock、活动 DDL；
- FK 依赖；
- Apply 中途失败与 Recovery Plan；
- post-check 异常后的恢复清单；
- Apply 完成且无 stamp；
- runtime 源码索引依赖扫描；
- manifest 7 项正反向合同；
- dry-run 数据库语句只允许 SELECT/PRAGMA。

### Schema / Drift / Adoption targeted tests

```text
52 passed
```

### Full pytest

```text
128 passed
```

没有新增失败。存在两个非本阶段失败项：Starlette/httpx2 弃用提示，以及当前 Windows 运行环境无法写 `.pytest_cache` 的权限警告。

## 9. Ruff

### 本阶段文件

```text
All checks passed!
```

### 全仓库

```text
10 x I001
```

均为 Stage 2 前已经存在的 import sorting 历史问题，分布在 `alembic/env.py` 和 9 个历史 migration。本阶段未新增 ruff 问题，也未扩大范围修复历史文件。

## 10. Fresh MySQL Regression

环境：隔离临时 `mysql:8.4`，实际版本 MySQL 8.4.11，独立容器、独立匿名数据层、仅回环端口，不连接生产 MySQL 数据卷。

首次尝试把临时容器内存上限设为 320MB，MySQL 初始化阶段触发容器 OOM；该已退出容器随即删除。将隔离容器上限调整为 512MB、buffer pool 设为 64MB 后，全套演练成功。该现象属于测试环境资源不足，不是 migration 或 Cleanup 逻辑失败；后续 MySQL CI/演练环境不应按 320MB 上限制定容量。

从真正空数据库执行：

```text
alembic upgrade head -> 20260909_001: PASS
Drift Checker: 0 ERROR, 42 WARNING
alembic check: No new upgrade operations detected
```

42 个 WARNING 分类：

- MySQL FK 自动索引：2；
- 字段级 server_default 白名单：40；
- 未知 WARNING：0。

Fresh SQLite 由自动迁移测试再次验证：全链通过、Drift Checker `0 ERROR / 40 WARNING`。

## 11. Production-like MySQL 演练

本轮没有从生产导出业务数据。演练库通过以下方式构造：

1. 隔离 MySQL 8.4.11 从空库执行完整 Alembic 链到 `20260909_001`；
2. 仅在该临时库执行 7 项 recovery SQL，精确恢复已只读核验的 Legacy 差异；
3. 将临时库 `alembic_version` 调整为 `20260908_001`；
4. 生成该临时库的真实 schema-only dump 和 SHA-256 备份证明。

演练结果：

### Test A：Dry Run

```text
LEGACY CLEANUP REQUIRED
6 DROP + 1 CREATE
exit 0
No changes were made.
```

### Test B：Apply

```text
LEGACY CLEANUP COMPLETE
7 operations succeeded
No stamp executed
```

### Test C：Drift

```text
0 ERROR
42 approved WARNING
unknown WARNING = 0
```

### Test D：Adoption Inspector

```text
SAFE TO ADOPT TO 20260909_001
```

### Test E：再次 Dry Run

```text
ALREADY CLEAN
No changes were made.
```

演练结束后已删除临时 MySQL 容器和 `/tmp/ai-study-stage25`。生产 `ai-study-backend`、`ai-study-web`、`ai-study-mysql`、`ai-study-redis` 容器保持运行；生产数据库没有执行任何 DDL、revision 更新或 stamp。

## 12. 当前是否具备生产 Cleanup 技术条件

结论：

## 技术实现和非生产验证已具备，但不能直接执行生产 Cleanup

仍需完成人工门槛：

1. 先部署经过审核的 Stage 1/2/2.5 代码，但部署本身必须单独批准；
2. 再次只读核验生产 commit、`20260908_001`、7 个对象和无额外 drift；
3. 用生产标准备份流程生成新备份及真实 backup-proof；
4. 检查服务器负载、长事务、metadata lock 和磁盘空间；
5. 人工确认仓库外 BI、手工 SQL、第三方客户端没有索引 hint 依赖；
6. 审核生产 dry-run 的 7 项和计划指纹；
7. 单独批准 `--apply`；
8. Cleanup 后重新运行 Drift Checker 与 Adoption Inspector；
9. 只有出现 `0 ERROR` 和 `SAFE TO ADOPT TO 20260909_001` 后，才能再次人工批准 stamp。

## 13. Diff 摘要

Stage 2.5 本轮增量：

```text
+ backend/app/core/legacy_cleanup_manifest.py
+ backend/app/core/legacy_cleanup.py
+ scripts/legacy_schema_cleanup_20260908.py
+ backend/tests/test_legacy_cleanup.py
+ docs/Alembic_Stage2.5_实施报告.md
M docs/Legacy_Production_Cleanup_Adoption_方案.md
```

本轮未 commit。当前工作区仍同时包含此前已验收但未提交的 Stage 1/Stage 2 文件，以及用户原有未跟踪文档/截图；后续准备 Commit A/B 时必须使用精确路径 `git add`，禁止 `git add .`。

## 14. 阶段边界

- 未修改生产数据库；
- 未部署；
- 未 stamp；
- 未执行生产 upgrade；
- 未移除生产 `create_all`；
- 未创建 commit；
- 未进入 Stage 3；
- 未进入 Phase 2。
