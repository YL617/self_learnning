# Alembic Stage 2 实施报告

日期：2026-09-08。范围：Schema 检查工具、冻结结构契约、测试、文档。

## 结论

**工具已实现，但 Stage 2 的 Fresh Schema 零错误验收未通过，不能进入 Stage 3。**

Fresh SQLite 和隔离 Fresh MySQL 8.4 都成功执行完整迁移到 `20260909_001`。
严格检查发现相同的 9 个 ORM 显式 `id` 索引缺失。此前检查错误地把显式索引与
主键隐式索引一起忽略，因此 Stage 1 的“基本一致”不能作为严格零漂移结论。

本轮未修改 migration、main.py、create_all、Docker 或部署脚本；未执行 stamp，
未连接生产数据库做核验或写入，未部署、未提交、未进入 Phase 2。

## 文件清单

- `backend/app/core/schema_drift.py`：结构比较、默认值精确白名单、分级输出及 CLI。
- `backend/app/core/adoption_inspector.py`：只读接管判断、实际迁移图验证、拒绝不确定状态。
- `backend/app/core/schema_reconciliation_manifest.py`：正式 manifest、40 项默认值白名单、9 项待迁移索引清单。
- `backend/app/core/schema_profiles.py`：冻结契约加载和受审核的 ORM 补充索引要求。
- `backend/app/core/schema_profiles.json`：真实 SQLite 迁移生成的 20260907/08/09 结构快照。
- `backend/tests/freeze_schema_profiles.py`：显式开发工具，只在临时 SQLite 空库重放迁移生成快照。
- `backend/tests/test_schema_tools.py`：28 项工具测试。
- `backend/tests/test_schema_migrations.py`：2 项真实迁移与 manifest 所有权测试。
- 本报告。

以上此前部分文件已在未提交工作区存在，本轮在其基础上修正。Stage 1 未提交迁移和用户的
ECS 文档、界面截图均保留，不混入额外提交。

## Drift Checker

比较表集合、字段集合、类型族、nullable、实际 server_default、PK、FK（含删除/更新规则）、
unique 和普通索引。普通索引及 PK 保留列顺序；unique 以唯一性覆盖的列集合比较。
不再忽略 ORM 显式声明的主键列普通索引。

输出 INFO（方言、表数、revision）、WARN（已知容许差异）、ERROR（真实漂移）。
CLI：`python -m app.core.schema_drift`。
退出码：0 无真实漂移；1 存在漂移；2 检查异常。异常不打印连接串或原始异常消息。
默认值错误输出属于 Schema 元数据，不读取业务内容。

## 默认值白名单

`ALLOWED_SERVER_DEFAULT_DIFFS` 共 40 项，每项记录 table、column、migration_default、
orm_default、reason。只有字段、数据库实际默认值、ORM Python 默认值描述均匹配，且
ORM 无 server_default 时，才返回 warning。白名单字段若值变为其他值，同样失败。
双方都有 server_default 但值不同也失败。

清单中 reconciliation 项涉及 plan_items、questions、wrong_book_items、documents、pets、users；
历史项涉及 user_profiles、users、plan_chat_sessions、pet_messages、pet_play_sessions、
ai_provider_snapshots、ai_usage_records、activation_codes、ai_daily_usage、focus_tags、
course_recommendations、courses、knowledge_points。完整逐字段值以 manifest 为准。

日期哨兵 `wrong_book_items.next_review_date = '1970-01-01'` 是现有迁移的兼容值，
不是业务上等价于 date.today；列入的是明确允许的已知差异，不是语义等价声明。

## 方言归一化

- BOOLEAN/BOOL 与显式 TINYINT(1) 同类；TINYINT(4) 不按 bool 处理。
- 字符串 collation 不作为类型族差异；本轮不检查字符长度、数值精度等族内参数。
- 当前时间函数 NOW()/CURRENT_TIMESTAMP 统一；数值按 Decimal 规范化，字符串保留大小写。
- FK RESTRICT 与 NO ACTION 按当前 SQLite/MySQL 的即时检查语义比较。
- MySQL PRIMARY 隐式索引不作为额外普通业务索引。
- FK 自动索引仅在 MySQL、列顺序恰好匹配 FK、名称符合 FK 名或首列自动命名时容许。
  这验证结构及命名规则，无法从 information_schema 追溯索引究竟由人还是引擎创建。
- 不同名字但等效的 unique constraint / unique index 以唯一性语义归一化。
  不检查重复等效唯一对象的数量，现有 file_analyze_results 重复唯一声明尚未处理。

## Manifest 与 Adoption

机器可读 manifest 包含 5 个 created tables（todos、reminders、shop_items、
plan_adjustment_logs、file_analyze_results）、6 张表的 16 个 added columns、
ix_course_recommendations_status，以及 20260908 的全部 historical managed objects。
结构内容含类型、nullability、default、PK/FK、unique/index，来源是冻结快照而非运行时建库。
工具和迁移测试共用此结构；未为了共用 manifest 改写历史 migration。

Inspector 先检查真实 ScriptDirectory：单 root、单 head、线性 down_revision、无分叉/合并。
然后读取唯一 version_num，匹配完整冻结结构，并检查当前 ORM。
当前支持 20260907、20260908、20260909 三个结构契约；更早、未知、缺失、多 revision，
或无法唯一匹配时保守 BLOCKED。识别出真实历史结构且与 revision 相等，才报告待执行迁移。
当前 ORM 完整终态另要求 manifest 明确记录的 9 个 ORM-only 索引存在；它们不是白名单。

只有完整终态结构可输出 SAFE TO ADOPT TO 20260909_001。
部分 reconciliation 已存在、部分缺失的混合库不能直接建议运行会重复建表的升级。
CLI：`python -m app.core.adoption_inspector`；SAFE 退出 0，其他结果退出 1。
工具没有写入模式或 stamp 参数；检查异常也 BLOCKED，并隐藏异常原文。
冻结快照生成器是单独开发工具，不属于 Inspector 执行路径。

## 验证结果

| 项目 | 结果 |
|---|---|
| 本轮修改前 pytest 基线 | 85 passed，1 个既有依赖弃用 warning |
| 当前 pytest | 105 passed，1 个相同 warning |
| 工具测试 | 28 passed |
| 真实迁移/manifest 测试 | 2 passed |
| 本轮文件 ruff | 通过 |
| 全仓库 ruff | 10 个既有 I001，位于 env.py 和旧 migration，未修改 |
| Fresh SQLite upgrade | 真正空库成功到 20260909_001 |
| Fresh SQLite drift | 9 ERROR、40 WARNING，退出 1 |
| Fresh MySQL 8.4 upgrade | SHOW TABLES 为空后，完整 upgrade head 成功 |
| Fresh MySQL drift | 9 ERROR、42 WARNING，退出 1 |
| graph | 16 个 revision，单线单 head 20260909_001 |

MySQL 测试运行在独立临时容器：network none，无主机端口，无生产卷，数据库 stage2_check；
内存上限 320 MB。测试使用现有后端镜像，覆盖临时挂载的迁移/检查工具，直接执行 Alembic，
不启动应用 lifespan。临时容器、匿名数据卷及上传目录已清理。

测试包括缺表/列、nullable、FK 动作、unique、非白名单默认值、错误白名单值、双方默认值不同、
多余业务索引、显式主键列索引缺失、MySQL FK 自动索引和类型归一化；Adoption 覆盖完整终态、
未记录或未知/多 revision、缺关键字段、缺业务索引、图异常、不确定结构和只读 SQL 断言。
实际历史 20260907/08 从空库重放后能正确输出 UPGRADE REQUIRED。

真实迁移测试明确断言并记录当前 9 个已知漂移，用于防止检查器重新静默忽略它们。
**pytest 通过不代表 Fresh 零漂移验收通过；后者当前失败。**

## 阻塞项

缺少以下显式普通索引，每个均为对应表的 id 单列索引：

- ix_activation_codes_id
- ix_ai_provider_snapshots_id
- ix_course_recommendations_id
- ix_focus_tags_id
- ix_pet_memories_id
- ix_pet_messages_id
- ix_pet_play_sessions_id
- ix_plan_chat_messages_id
- ix_plan_chat_sessions_id

这些索引在查询能力上可能冗余，因为已有 PK，但按当前用户要求及 ORM 显式结构约定，
不能直接当数据库隐式主键索引而忽略。建议后续单独确认：补迁移以匹配 ORM，或明确允许
移除 ORM 中冗余索引声明。两种选择均涉及当前 Stage 2 之外的 Schema 契约变更，本轮未执行。

## 生产 dry-run 推断

没有对本轮生产数据库运行 Inspector。已知之前记录的 revision 是 20260908_001，
历史只读结果指出 ix_course_recommendations_status 缺失。
**基于该记录的保守推断是 ADOPTION BLOCKED，不能报告 SAFE。**
之前数据不足以证明所有 FK/default/index 均符合新规则；当前线上是否又有变动未知。
正式接管前需要使用本轮工具重新只读核验，并先解决本报告的新库漂移。

当前停止在 Stage 2，不部署、不进入 Stage 3、不进入 Phase 2。
