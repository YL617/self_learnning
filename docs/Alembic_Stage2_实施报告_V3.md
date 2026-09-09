# Alembic Stage 2 实施报告 V3

日期：2026-09-08

## 结论

Stage 2 工具和 Fresh Schema 验收通过。Fresh SQLite 与 Fresh MySQL 8.4 均可从真正空库
升级到 `20260909_001`，Drift Checker 均为 0 ERROR，Alembic check 均无差异；全量测试通过，
未知 WARNING 为 0。

生产数据库只读 dry-run 结论为 `ADOPTION BLOCKED`。阻塞项是 6 个线上遗留的冗余 id
普通索引，以及缺失的 `ix_course_recommendations_status`。本轮未 stamp、未 upgrade、未 DROP
线上索引、未修改生产 Schema、未部署，也未进入 Stage 3 或 Phase 2。

## ORM Metadata 真实目标

`Base.metadata.tables["file_analyze_results"].c.document_id` 的实际状态：

- `unique=True`
- `index=True`
- constraints：只有 `PrimaryKeyConstraint(id)` 和 `ForeignKeyConstraint(document_id)`
- indexes：`ix_file_analyze_results_id` 普通索引，以及
  `ix_file_analyze_results_document_id(document_id)`、`unique=True`
- metadata 中没有 `UniqueConstraint(document_id)`

因此最终目标是一个唯一索引，不是 UniqueConstraint，也不是两者并存。

## Migration 最小修复

只从尚未提交、尚未部署的 `20260909_001_schema_reconciliation.py` 中移除：

```python
sa.UniqueConstraint("document_id", name="uq_file_analyze_results_document_id")
```

保留：

```python
op.create_index(
    "ix_file_analyze_results_document_id",
    "file_analyze_results",
    ["document_id"],
    unique=True,
)
```

对应 downgrade 仍先删除该唯一索引，再删除表。revision、down_revision、其他表和其他迁移
均未因本次修复改变。没有新增修复 migration。

冻结结构契约 `schema_profiles.json` 通过真实迁移重放重新生成；迁移验收测试由“应识别已知
重复对象”恢复为“Fresh 零漂移”。Drift Checker 的比较与忽略规则没有为本修复放宽。

## Fresh SQLite

- 新建空 SQLite 数据库：成功。
- `alembic upgrade head`：成功，current 为 `20260909_001`。
- Drift Checker：`0 ERROR / 40 WARNING`，退出码 0。
- `alembic check`：`No new upgrade operations detected`。
- 重复唯一对象：已消失。
- 9 个已清理 ORM id 索引差异：0。

## Fresh MySQL 8.4

- `SHOW TABLES` 确认测试数据库为空。
- `alembic upgrade head`：完整链成功，current 为 `20260909_001`。
- Drift Checker：`0 ERROR / 42 WARNING`，退出码 0。
- `alembic check`：`No new upgrade operations detected`。
- 重复唯一对象：已消失。
- 9 个已清理 ORM id 索引差异：0。

MySQL 验证使用隔离临时容器，无主机端口、无生产卷，限制 320 MB 内存。验证结束后容器、
匿名数据卷、服务器临时目录和临时连接变量文件均已删除。

## WARNING 分类

| 分类 | SQLite | MySQL | 说明 |
|---|---:|---:|---|
| MySQL FK 自动索引 | 0 | 2 | activation_codes.created_by / used_by |
| server_default 字段级白名单 | 40 | 40 | 字段、迁移值、ORM 默认值和原因均精确匹配 |
| Boolean/TINYINT 等价 | 0 | 0 | 作为已批准类型归一化，不产生 warning |
| Collation 等价 | 0 | 0 | 作为已批准类型归一化，不产生 warning |
| 其他 | 0 | 0 | 无未知 warning |

WARNING 数量与 V2 前保持一致，没有通过修改 warning 分类规则取得绿色结果。

## 测试与代码质量

- 全量 pytest：`107 passed`。
- 迁移、Drift、Adoption 针对性测试：`32 passed`。
- Adoption 逻辑测试：11 项全部通过。
- 本轮文件 ruff：通过。
- 全仓库 ruff：仍有 10 个既有 I001 导入排序问题，位于 `alembic/env.py` 和 9 个旧
  migration；本轮未顺手修改。
- `git diff --check`：通过；仅显示 Git 的 LF/CRLF 提示，无空白错误。

pytest 另报告 2 个非失败 warning：一个第三方依赖弃用提示，一个本机 `.pytest_cache`
写权限提示。均不影响测试结论，也不是本轮新增代码失败。

## 生产 Adoption Dry-run

通过临时工具容器连接生产 MySQL，只执行 SQLAlchemy Inspector 和
`SELECT version_num FROM alembic_version` 等结构查询。未查询业务数据。

结果：

```text
ADOPTION BLOCKED
dialect=mysql
revision=20260908_001
Expected one trusted schema match; got []
```

实际阻塞差异：

| Table | Index | Columns | 差异 |
|---|---|---|---|
| activation_codes | ix_activation_codes_id | id | DB 多余 |
| ai_provider_snapshots | ix_ai_provider_snapshots_id | id | DB 多余 |
| pet_messages | ix_pet_messages_id | id | DB 多余 |
| pet_play_sessions | ix_pet_play_sessions_id | id | DB 多余 |
| plan_chat_messages | ix_plan_chat_messages_id | id | DB 多余 |
| plan_chat_sessions | ix_plan_chat_sessions_id | id | DB 多余 |
| course_recommendations | ix_course_recommendations_status | status | DB 缺失 |

前 6 项是 ORM 已删除 `primary_key=True + index=True` 后留下的历史冗余普通索引。它们不是
MySQL PK 隐式索引：具有独立名称，且 Inspector 将其作为普通索引返回。主键自身已经提供
索引能力，ORM 不再声明这些对象，因此必须如实作为 extra business index 阻塞 adoption。

第 7 项是 reconciliation 明确应补齐的 status 业务索引；生产当前 revision 仍是
`20260908_001`，尚未执行 reconciliation，因此缺失符合现状，但不能直接 stamp 跳过。

Inspector 没有扩大白名单，也没有自动执行 stamp。第一次因临时容器读取到默认 SQLite 而
fail-closed；确认未连接生产后，改用生产容器现有 DATABASE_URL 的临时受限副本重新执行。
该临时文件权限为 600，执行后已删除，连接值未输出。

## 最终验收

| 验收条件 | 结果 |
|---|---|
| pytest 全通过 | 通过 |
| 本轮 ruff 通过 | 通过 |
| Fresh SQLite 0 ERROR | 通过 |
| Fresh MySQL 0 ERROR | 通过 |
| Alembic check | 通过 |
| 明确允许的 WARNING | 通过 |
| unknown WARNING = 0 | 通过 |
| Adoption 测试 | 通过 |
| 生产 dry-run 结论明确 | 通过：ADOPTION BLOCKED |

结论：**Stage 2 的工具开发与 Fresh Schema 验收完成。生产数据库尚不可 adoption。**
后续需要独立设计 production cleanup migration：在执行 reconciliation 的同时，明确处理
6 个冗余索引；在该方案获批前不得 stamp 或修改生产数据库。
