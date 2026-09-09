# Legacy Production Cleanup + Adoption 方案

> 阶段：Alembic Stage 2.5 设计
> 范围：生产数据库只读核验结果基础上的一次性清理与 Alembic 接管方案
> 当前生产基线：应用提交 `a7c3e64`，Alembic revision `20260908_001`
> 本文只描述未来执行方法；本轮未执行 `DROP INDEX`、`CREATE INDEX`、`stamp`、`upgrade` 或部署。

## 1. 结论

当前生产数据库与目标 Schema `20260909_001` 之间有 7 项真实差异：

- 6 个生产遗留的、ORM 已不再声明的 `id` 普通索引；
- 缺少 ORM 明确声明的普通索引 `ix_course_recommendations_status(status)`。

这 7 项只存在于 Legacy Production 的历史状态，不应加入所有 Fresh Database 都要执行的普通 Alembic 迁移链。推荐在进入 adoption 前，使用独立的一次性显式 Cleanup Script 完成修正；修正后必须再次由 Drift Checker 和 Adoption Inspector 证明 Schema 等价，才能由人工单独执行 `alembic stamp 20260909_001`。

最终判断：

## 可以，但以下项需人工确认

1. 执行前的新备份已成功完成，文件非空，并已记录路径、大小、时间和校验值；
2. 执行窗口内没有长事务或元数据锁阻塞，业务处于低流量或维护窗口；
3. 仓库外的运维 SQL、报表 SQL、第三方客户端没有按名称强制引用 6 个遗留索引；
4. Apply 前重新核验的 commit、revision、表引擎及 7 个索引定义与本文完全一致；
5. 操作人员理解 7 条 MySQL DDL 不是一个可整体回滚的事务，并准备好逐项恢复 SQL。

## 2. 已确认事实与证据边界

### 2.1 已确认事实

- 7 张目标表均为 `InnoDB`。
- 6 个待删除对象均为单列 `id`、`BTREE`、可见、非唯一普通索引，无前缀长度。
- 6 张表各自另有独立的 `PRIMARY(id)`，该主键索引为唯一索引。
- 6 个普通索引均不是 `PRIMARY`、不是 `UNIQUE` 业务约束，也没有同名数据库约束。
- 目标表中只有 `plan_chat_sessions.id` 被入站外键引用：`plan_chat_messages.session_id -> plan_chat_sessions.id`；删除额外普通索引后，`PRIMARY(id)` 仍完整覆盖被引用键。
- 没有外键把这 6 张表的 `id` 作为子表约束列，因此不存在删除后缺少子表 FK 支撑索引的问题。
- 仓库代码未发现 `USE INDEX`、`FORCE INDEX`、`IGNORE INDEX`，也未发现对 6 个遗留索引名称的显式引用。
- ORM 的 `CourseRecommendation.status` 使用 `index=True`；Fresh reconciliation 创建的是单列、非唯一普通索引 `ix_course_recommendations_status`。
- 生产 `course_recommendations` 只有 `PRIMARY(id)` 以及 `course_id`、`plan_id`、`user_id` 三个普通索引，没有 `status` 索引，也没有不同名称但等价的单列 `status` 索引。

### 2.2 尚不能由仓库证明的事项

仓库搜索不能覆盖数据库外部的手工 SQL、BI/报表工具、第三方客户端或未纳入版本管理的运维脚本。因此，“没有按索引名称强制引用”在仓库范围内已确认，在所有外部系统范围内仍属于未知信息。实际 Apply 前必须由运维人员确认；无法确认时应保留为人工审核门槛，而不是由脚本忽略。

## 3. 六个遗留索引精确清单

| table | index_name | columns | unique | 对应 PK | ORM 当前声明 | FK/约束依赖 | 删除后 PK 覆盖 | 仓库内名称引用 | 结论 |
|---|---|---|---|---|---|---|---|---|---|
| `activation_codes` | `ix_activation_codes_id` | `id` | 否 | `PRIMARY(id)` | 否 | 无；表内其他 FK 位于 `created_by/used_by` | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |
| `ai_provider_snapshots` | `ix_ai_provider_snapshots_id` | `id` | 否 | `PRIMARY(id)` | 否 | 无 | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |
| `pet_messages` | `ix_pet_messages_id` | `id` | 否 | `PRIMARY(id)` | 否 | 无；表内 FK 位于 `pet_id` | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |
| `pet_play_sessions` | `ix_pet_play_sessions_id` | `id` | 否 | `PRIMARY(id)` | 否 | 无；表内 FK 位于 `pet_id` | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |
| `plan_chat_messages` | `ix_plan_chat_messages_id` | `id` | 否 | `PRIMARY(id)` | 否 | 无；表内 FK 位于 `session_id` | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |
| `plan_chat_sessions` | `ix_plan_chat_sessions_id` | `id` | 否 | `PRIMARY(id)` | 否 | `plan_chat_messages.session_id` 引用该列，但 `PRIMARY(id)` 是有效替代索引 | 是 | 未发现 | 可删除，外部 SQL 需人工确认 |

六个对象还同时满足：

- 不是全文索引、空间索引、前缀索引、函数索引或不可见索引；
- 不属于复合索引的一部分；
- 删除不改变 PK、FK、unique 或列定义；
- 删除后不会要求 MySQL 重建同名普通索引。`plan_chat_sessions.id` 的入站 FK 仍由主键索引满足引用键索引要求。

因此，从已取得的生产 metadata、ORM metadata 和仓库代码看，六项均具备安全删除条件。唯一未封闭的信息是仓库外是否有人按索引名写过 index hint。

## 4. 缺失索引验证

目标索引：

```text
table: course_recommendations
index: ix_course_recommendations_status
columns: (status)
unique: false
type: BTREE
```

验证结果：

- ORM 明确声明 `CourseRecommendation.status = mapped_column(..., index=True)`；
- Fresh MySQL 的 `20260909_001_schema_reconciliation.py` 明确创建该非唯一索引；
- 生产数据库中该索引不存在；
- 生产也不存在不同名称但同样只覆盖 `(status)` 的等价索引；
- 现有 `course_id/plan_id/user_id` 索引不能替代按 `status` 开头的查询路径。

因此 Legacy Cleanup 应创建且只创建一个非唯一单列索引：

```sql
CREATE INDEX `ix_course_recommendations_status`
    ON `course_recommendations` (`status`);
```

## 5. Cleanup Script 设计

建议未来新增：

```text
scripts/legacy_schema_cleanup_20260908.py
```

该脚本应是一个深模块：对操作者只暴露很小的 CLI Interface，把 metadata 核验、执行顺序、逐项后验、日志脱敏和失败封闭留在 Implementation 内部。它不应承担普通 drift 检测或 adoption 判断；这两个职责继续由现有 Drift Checker 与 Adoption Inspector 负责，三者通过同一份机器可读 manifest 形成清晰边界。

### 5.1 CLI Interface

```bash
# 默认只读
python scripts/legacy_schema_cleanup_20260908.py

# 显式执行；建议要求带上 dry-run 生成的计划指纹
python scripts/legacy_schema_cleanup_20260908.py \
  --apply \
  --expected-revision 20260908_001 \
  --plan-fingerprint <dry-run-output-fingerprint>
```

脚本必须复用现有 `get_settings().DATABASE_URL` 或项目统一数据库配置，不接受命令行明文密码，不打印连接串。

### 5.2 默认 Dry Run

Dry Run 只允许读取：

- 数据库方言和版本；
- `alembic_version`；
- `information_schema` / SQLAlchemy Inspector 中的表、列、索引、PK、FK、unique 和引擎 metadata；
- 当前代码中的 reconciliation manifest。

成功匹配预期 Legacy 状态时输出：

```text
LEGACY CLEANUP REQUIRED
INFO dialect=mysql
INFO revision=20260908_001

CREATE:
course_recommendations.ix_course_recommendations_status(status)

DROP:
activation_codes.ix_activation_codes_id(id)
ai_provider_snapshots.ix_ai_provider_snapshots_id(id)
pet_messages.ix_pet_messages_id(id)
pet_play_sessions.ix_pet_play_sessions_id(id)
plan_chat_messages.ix_plan_chat_messages_id(id)
plan_chat_sessions.ix_plan_chat_sessions_id(id)

TARGET:
Schema equivalent to 20260909_001
PLAN FINGERPRINT: <sha256-of-canonical-plan>
```

Dry Run 不生成 DDL 副作用，不执行 `stamp`，退出码建议为：

- `0`：状态与预期完全一致，已生成可审核计划；
- 非 `0`：`CLEANUP BLOCKED`，至少一个前置条件不成立。

### 5.3 显式 Apply

Apply 模式必须先重新执行完整 Dry Run 检查，并验证计划指纹；不能信任上一次检查的结果。建议按以下顺序执行：

1. 创建 `ix_course_recommendations_status`；
2. 验证其名称、列顺序、非唯一、BTREE 和可见性；
3. 按固定清单逐个删除 6 个冗余索引；
4. 每删除一个后，立刻验证目标索引消失、`PRIMARY(id)` 仍存在、相关 FK/constraint 未变化；
5. 所有步骤完成后，脚本只报告 Cleanup 完成，不执行 `stamp`。

先创建缺失索引的原因：如果第一条 DDL 失败，生产尚未发生任何删除；如果随后某个删除步骤失败，已经成功创建的业务索引仍是有益且可逆的变更。脚本不得自动改变顺序、自动降级锁级别或跳过失败项。

### 5.4 日志约束

日志只允许包含：

- `dialect`；
- `revision`；
- `table`；
- `index`；
- `operation`；
- `success/failure`；
- 脱敏后的异常类型和 MySQL 错误码。

禁止输出连接字符串、用户名、密码、Secret、Token、业务行数据或 SQL 参数中的敏感值。

## 6. Fail-closed 条件

以下任一条件成立，Dry Run 或 Apply 必须输出 `CLEANUP BLOCKED` 并以非零状态退出：

- 方言不是 MySQL，或目标表不是 InnoDB；
- `alembic_version` 不存在、不是单行，或 revision 不等于 `20260908_001`；
- migration graph 不是预期的单线、单 head；
- 任一目标表、`id` 列、PK 或 `status` 列不存在；
- 任一待删除索引不存在，或名称、列顺序、唯一性、类型、可见性、前缀属性与预期不符；
- 待删除索引是 PK、unique、constraint backing index、FK 唯一可用索引或特殊索引；
- `course_recommendations.status` 已存在一个等价的其他名称索引；
- `ix_course_recommendations_status` 已存在但定义不匹配；
- 发现清单外的真实 drift，或 Drift Checker 在基线状态上出现新的未知差异；
- Apply 时计划指纹与人工审核的 Dry Run 指纹不同；
- 任何一步 DDL 执行失败或后验检查失败；
- 数据库连接被配置为 SQLite、测试库或无法确认的目标；
- 备份未成功完成或无法确认非空。

脚本不得使用 `IF EXISTS` / `IF NOT EXISTS` 把状态不一致静默吞掉。部分执行后的再次运行也必须先报告当前实际状态和已完成步骤，默认阻塞，由人工决定恢复还是在复核后继续。

## 7. MySQL 8.4 DDL 行为与锁风险

MySQL 8.4 对 InnoDB 的单条索引 DDL 提供原子 DDL：单条语句要么提交，要么回滚，即使服务器在执行中停止，也能由数据字典和 DDL log 恢复。但这不是“事务型 DDL”；DDL 会隐式结束当前事务，7 条语句不能放在一个事务里整体回滚。[MySQL 8.4 Atomic DDL](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)、[Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)

对 InnoDB 二级索引，创建索引支持 in-place、允许并发 DML、不重建表，但不是纯 metadata 操作；删除索引支持 in-place、允许并发 DML、不重建表，并且只修改 metadata。[MySQL 8.4 Online DDL Operations](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html)

即使使用 Online DDL，初始化与提交表定义阶段仍需要短暂的排他 metadata lock。长事务可能让 DDL 等待；待处理的排他 metadata lock 又可能阻塞后续访问。Apply 前必须检查长事务和 metadata lock，并设置有限的 `lock_wait_timeout`，避免无限等待。[Online DDL Performance and Concurrency](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-performance.html)、[Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)

创建索引还可能因磁盘临时空间不足、在线 DDL 日志溢出、锁超时或不兼容的 `ALGORITHM/LOCK` 请求失败。[Online DDL Failure Conditions](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-failure-conditions.html)

未来 Apply 工具可以显式请求：

```sql
SET SESSION lock_wait_timeout = 30;

ALTER TABLE `course_recommendations`
    ADD INDEX `ix_course_recommendations_status` (`status`),
    ALGORITHM=INPLACE,
    LOCK=NONE;

ALTER TABLE `<table>`
    DROP INDEX `<index>`,
    ALGORITHM=INPLACE,
    LOCK=NONE;
```

如果 MySQL 拒绝 `ALGORITHM=INPLACE` 或 `LOCK=NONE`，脚本必须停止，不能自动回退到 `COPY`、`SHARED` 或 `EXCLUSIVE`。是否在维护窗口用更宽松的锁策略，应另行人工评估。

## 8. Legacy Cleanup Recovery Plan

以下是逐项反向操作。它们是恢复 SQL，不是事务 rollback；只有在确认当前实际状态后才能人工执行。

### 8.1 恢复被删除的六个索引

```sql
CREATE INDEX `ix_activation_codes_id`
    ON `activation_codes` (`id`);

CREATE INDEX `ix_ai_provider_snapshots_id`
    ON `ai_provider_snapshots` (`id`);

CREATE INDEX `ix_pet_messages_id`
    ON `pet_messages` (`id`);

CREATE INDEX `ix_pet_play_sessions_id`
    ON `pet_play_sessions` (`id`);

CREATE INDEX `ix_plan_chat_messages_id`
    ON `plan_chat_messages` (`id`);

CREATE INDEX `ix_plan_chat_sessions_id`
    ON `plan_chat_sessions` (`id`);
```

恢复时仍应采用逐项前置检查、单条执行、单条后验验证；不得盲目整段执行。

### 8.2 撤销新建的 status 索引

```sql
DROP INDEX `ix_course_recommendations_status`
    ON `course_recommendations`;
```

若 Cleanup 在中途停止，应先根据实际 Schema 生成“已成功 / 未执行 / 定义异常”的状态表，再选择：

- 按反向 SQL 恢复到原始 `20260908_001` Legacy 状态；或
- 在重新核验、重新备份和人工批准后完成剩余操作。

自动脚本不能自行选择其中任何路径。

## 9. 生产完整执行顺序

### Gate 1：部署与数据库基线

1. 确认服务器当前应用 commit 是审核批准的版本；
2. 确认 Git 工作区没有会影响 Schema 工具的未知修改；
3. 只读确认 `alembic current = 20260908_001`；
4. 确认 Alembic graph 单线、head 为 `20260909_001`；
5. 确认 7 张目标表均为 InnoDB；
6. 检查磁盘空间、长事务、metadata lock 等待和当前流量。

### Gate 2：备份

1. 使用项目标准脚本 `scripts/backup_mysql.sh` 执行新备份；
2. 必须以脚本退出码 `0` 为基础条件；
3. 确认备份文件存在且非空，记录绝对路径、字节数、mtime 和 SHA-256；
4. 确认备份不是一个被同日文件名意外覆盖却未完整写入的空文件；
5. 高可靠要求下，应在隔离数据库做恢复演练。只检查文件存在不能证明可恢复。

任何一项失败，停止。

### Gate 3：Cleanup Dry Run 与人工确认

1. 运行 Cleanup Script 默认模式；
2. 输出必须严格为 1 个 CREATE、6 个 DROP、目标 `20260909_001`；
3. 人工逐项比对本文清单；
4. 记录 plan fingerprint；
5. 明确确认仓库外没有索引 hint 依赖。

### Gate 4：Cleanup Apply

1. 使用 `--apply --expected-revision 20260908_001 --plan-fingerprint ...`；
2. Apply 内部重新执行全部前置检查；
3. 创建 status 索引并后验；
4. 逐个删除 6 个遗留索引并逐个后验；
5. 遇到任一失败立即停止，不执行后续项；
6. 不执行 `stamp`。

### Gate 5：Cleanup 后验收

必须同时满足：

```text
Drift Checker: 0 ERROR
Unknown WARNING: 0
Adoption Inspector: SAFE TO ADOPT TO 20260909_001
```

并人工确认：

- 6 个遗留索引均不存在；
- `ix_course_recommendations_status(status)` 存在且非唯一；
- 所有 PK、FK、unique 和其余业务索引未变化；
- 核心 API、health 和数据库连接正常。

若 Inspector 仍输出 `ADOPTION BLOCKED`，禁止 stamp。

### Gate 6：Adoption 人工确认与 stamp

只有 Gate 5 全部通过后，单独进行第二次人工确认，再执行：

```bash
alembic stamp 20260909_001
```

该操作只更新 Alembic revision 记录，不执行 `20260909_001` 的 DDL。其语义是：数据库已经通过历史 `create_all`、既有迁移和经审核的 Legacy Cleanup 达到该 revision 的等价 Schema。

### Gate 7：stamp 后验收

1. `alembic current` 必须显示 `20260909_001`；
2. `alembic upgrade head` 必须无 DDL、无待执行 revision；
3. Drift Checker 必须为 `0 ERROR`；
4. Adoption Inspector / revision 检查必须一致；
5. 后端 health、登录和核心只读接口正常；
6. 记录执行人、时间、备份、每条 DDL 结果和最终 revision，不记录 Secret。

## 10. 风险评估

| 风险 | 可能影响 | 控制措施 |
|---|---|---|
| 长事务持有 metadata lock | DDL 等待，后续请求也可能排队 | 低流量窗口；执行前检查；有限 `lock_wait_timeout` |
| 创建 status 索引消耗 CPU、I/O、临时空间 | 2 核 2G 主机短时负载升高 | 检查磁盘和负载；维护窗口；禁止自动回退 COPY |
| 多条 DDL 无法整体回滚 | 中途形成部分完成状态 | 固定顺序；逐项前后验；每项恢复 SQL；失败即停 |
| 外部 SQL 使用 index hint | DROP 后外部查询报错 | 由运维确认仓库外 SQL；无法确认则人工审核，不自动执行 |
| 备份文件不可恢复 | 故障时恢复能力不足 | 非空、校验值、记录路径；高可靠场景做隔离恢复演练 |
| Schema 在 Dry Run 与 Apply 间变化 | 计划依据失效 | Apply 重查；计划指纹；revision 和 metadata 严格匹配 |
| 错把 cleanup 和 stamp 连续自动化 | 未验证 Schema 就宣称已接管 | 两个人工 Gate；Cleanup 工具永不执行 stamp |

## 11. 架构边界

- `20260909_001_schema_reconciliation.py` 必须保留，继续负责 Fresh Database 从迁移链得到完整当前 Schema。
- Cleanup Script 只处理已确认的 `20260908_001` Legacy Production 状态，不进入普通 migration graph。
- Drift Checker 继续严格比较 ORM、Fresh Alembic Schema 和 Production Schema，不为这 6 个对象增加忽略项。
- Adoption Inspector 继续只读、fail-closed，只给出是否可接管的结论，不执行 stamp。
- `alembic stamp` 保持为独立人工运维动作。

这组边界保证最终目标仍然是：

```text
ORM Schema
= Fresh Alembic Schema
= Adopted Production Schema
```

而不是长期维护一套被检测器忽略的生产特例。

## 12. 本轮状态

- 已补充生产只读 metadata 核验；
- 已完成 Cleanup + Adoption 设计；
- 已实现 `scripts/legacy_schema_cleanup_20260908.py`；
- 已实现机器可读 cleanup/recovery manifest；
- 已在隔离 MySQL 8.4.11 中完成 Production-like dry-run、apply、drift、adoption 和再次 dry-run 演练；
- 演练结果为 cleanup 后 `0 ERROR`、`SAFE TO ADOPT TO 20260909_001`、再次运行 `ALREADY CLEAN`；
- 临时 MySQL 容器和 `/tmp` 演练目录已清理；
- 未修改任何 migration；
- 未修改生产数据库；
- 未执行 `DROP INDEX`、`CREATE INDEX`、`stamp`、`upgrade` 或部署；
- 未进入 Stage 3；
- 未进入 Phase 2。
