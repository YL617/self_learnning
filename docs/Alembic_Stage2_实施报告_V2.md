# Alembic Stage 2 实施报告 V2

日期：2026-09-08

## 结论

9 个冗余 ORM 主键普通索引已按批准方案完成 Metadata 清理，未新增或修改数据库 migration。
这 9 项不再造成 Fresh SQLite/MySQL drift，也不再出现在 `alembic check` 差异中。

Stage 2 **尚未通过最终验收**。严格检查新发现 `file_analyze_results.document_id`
同时存在唯一约束和唯一索引，而 ORM 只声明一个唯一索引。Fresh SQLite/MySQL 均为
1 ERROR；`alembic check` 同样要求移除多余唯一对象。本轮未获得修改 reconciliation
migration 的授权，因此没有扩大范围处理。

未部署、未 stamp、未运行生产 upgrade、未进入 Stage 3 或 Phase 2。

## 9 个索引精确审计

修改前定义均为 `id: Mapped[int] = mapped_column(primary_key=True, index=True)`；
修改后仅移除 `index=True`。所有字段仍为 Integer、NOT NULL、单列 PK，无 FK、unique、
default 或 server_default；表内没有包含 id 的复合业务索引。仓库代码未引用下列索引名。

| Model 文件 | Table | Column | ORM 索引名 | DB 已有 PK | 生产是否存在该普通索引 |
|---|---|---|---|---|---|
| `models/billing.py` | activation_codes | id | ix_activation_codes_id | 是 | 是 |
| `models/ai_monitor.py` | ai_provider_snapshots | id | ix_ai_provider_snapshots_id | 是 | 是 |
| `models/ops.py` | course_recommendations | id | ix_course_recommendations_id | 是 | 否 |
| `models/engagement.py` | focus_tags | id | ix_focus_tags_id | 是 | 否 |
| `models/engagement.py` | pet_memories | id | ix_pet_memories_id | 是 | 否 |
| `models/engagement.py` | pet_messages | id | ix_pet_messages_id | 是 | 是 |
| `models/engagement.py` | pet_play_sessions | id | ix_pet_play_sessions_id | 是 | 是 |
| `models/plan_chat.py` | plan_chat_messages | id | ix_plan_chat_messages_id | 是 | 是 |
| `models/plan_chat.py` | plan_chat_sessions | id | ix_plan_chat_sessions_id | 是 | 是 |

生产索引存在性通过 SQLAlchemy Inspector 只读查询确认，只查询索引元数据，不查询业务数据。
生产共存在 6 个、缺少 3 个。按用户要求，本轮只报告，未执行 DROP INDEX。

## ORM 修改

修改 5 个模型文件，共删除 9 处 `index=True`：

- `backend/app/models/billing.py`：ActivationCode.id
- `backend/app/models/ai_monitor.py`：AiProviderSnapshot.id
- `backend/app/models/ops.py`：CourseRecommendation.id
- `backend/app/models/engagement.py`：FocusTag.id、PetPlaySession.id、PetMessage.id、PetMemory.id
- `backend/app/models/plan_chat.py`：PlanChatSession.id、PlanChatMessage.id

没有修改类型、PK、autoincrement、nullable、FK、unique、default 或 server_default。
没有创建新 migration，也没有生成 DROP INDEX migration。

## Drift Checker 语义

- ORM 显式业务普通索引仍必须在数据库中存在，否则 ERROR。
- 数据库 PK 隐式索引不作为 extra business index。
- MySQL FK 自动索引只有在方言、列顺序和命名来源均可证明时才作为 WARNING。
- server_default 仍按字段级白名单逐项核对实际值和 ORM Python 默认值。
- 新增重复唯一对象检测：同列由不同名称重复提供唯一性时 ERROR。

因此没有恢复“忽略所有 PK id 索引差异”的宽松规则。

## Fresh SQLite

- 真正空数据库执行 `alembic upgrade head`：成功，到 `20260909_001`。
- Drift：1 ERROR、40 WARNING，退出码 1。
- 9 个 id 索引错误：0。
- ERROR：`file_analyze_results.document_id` 同时存在
  `uq_file_analyze_results_document_id` 和 `ix_file_analyze_results_document_id`。
- `alembic check`：失败；要求移除额外唯一约束。

## Fresh MySQL 8.4

- `SHOW TABLES` 确认空库后执行完整 `alembic upgrade head`：成功，到 `20260909_001`。
- Drift：1 ERROR、42 WARNING，退出码 1。
- 9 个 id 索引错误：0。
- ERROR：与 SQLite 相同的重复唯一对象。
- `alembic check`：失败；要求移除额外唯一索引对象。

MySQL 运行在隔离临时容器，无主机端口、无生产卷、限制 320 MB 内存；测试完成后容器、
匿名数据卷和服务器临时目录已清理。未连接生产数据库执行 migration。

## WARNING 分类

| 分类 | SQLite | MySQL | 结论 |
|---|---:|---:|---|
| A. MySQL FK 自动索引 | 0 | 2 | 已批准规则；created_by、used_by |
| B. server_default 字段白名单 | 40 | 40 | 每项核对字段、实际值、ORM 默认和原因 |
| C. Boolean/TINYINT 等价 | 0 | 0 | 静默类型归一化，不产生 warning |
| D. Collation 等价 | 0 | 0 | 静默类型归一化，不产生 warning |
| E. 其他 | 0 | 0 | 满足必须为 0 的要求 |

全部 WARNING 均来自已批准规则，没有未知 warning。当前失败来自 ERROR，不是 warning。

## 测试与 Ruff

- 完整 pytest：107 passed，另有 2 个非测试失败 warning（依赖弃用、pytest cache 无写权限）。
- Adoption 逻辑测试：11 项，覆盖安全终态、真实升级、未知/缺失/多 revision、结构冲突、
  缺关键字段/索引、迁移图异常、结构匹配不唯一和只读 SQL。
- 本轮文件 ruff：通过。
- 全仓库 ruff：10 个既有 I001 导入排序问题；位于 `alembic/env.py` 和 9 个旧 migration。
  本轮未顺手修改。
- 新增问题：0 个 ruff 问题。

## 生产 Adoption Dry-run

按验收顺序，Fresh drift 尚未达到 0 ERROR，因此**没有运行新版生产 Adoption Inspector**。
这不是 SAFE 结论。

当前可确认的只读事实：

- 先前生产 revision：`20260908_001`；本轮没有重新查询 revision。
- 先前生产核验显示 `ix_course_recommendations_status` 缺失。
- 本轮确认 9 个冗余 id 普通索引中，生产存在 6 个。

在严格规则下，以上已足以得出保守结论：**ADOPTION BLOCKED**。即使先解决 Fresh 的重复
唯一对象，生产仍可能因缺少 status 索引和 6 个额外业务索引而阻塞。不能通过扩大忽略规则
得到 SAFE；后续应先确认 reconciliation migration 的重复唯一声明修复，再只读运行完整 Inspector，
最后单独设计生产遗留索引处理。

## Stage 2 验收判断

| 条件 | 状态 |
|---|---|
| pytest 全通过 | 通过 |
| 本轮 ruff 通过 | 通过 |
| Fresh SQLite 0 ERROR | 未通过：1 ERROR |
| Fresh MySQL 0 ERROR | 未通过：1 ERROR |
| 未知 WARNING = 0 | 通过 |
| Adoption tests | 通过 |
| 生产结论明确 | BLOCKED，未执行新版完整 dry-run |

最终判断：**Stage 2 未完成，不具备进入 Stage 3 的条件。**

下一步需要单独确认是否允许对尚未提交、尚未部署的 `20260909_001_schema_reconciliation.py`
做最小修复：保留 `ix_file_analyze_results_document_id` 唯一索引，移除重复的
`uq_file_analyze_results_document_id` 唯一约束。确认前不修改 migration。
