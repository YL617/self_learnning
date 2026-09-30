# Phase 2 题目 ↔ 知识点关联 · 设计审计报告

> 审计时间：2026-10-01 ｜ 审计方式：只读（本地代码 + 生产库只读查询）｜ 状态：待用户确认后进入实现
>
> 前置状态：Stage 3 Production Cutover COMPLETE，main = `4591cfc`，Alembic head = `20260909_001`，Schema 指纹 `095bf987…`（33 表）。本轮**未修改任何文件**。

---

## 1. 当前 Question 数据模型

`backend/app/models/learning.py`：

- `Question`：`id / user_id / document_id / subject(String 100) / knowledge_point(String 200, NOT NULL, 无索引) / question_type / stem / options_json / answer / analysis / source(默认 "ai") / is_favorite / created_at`
- `AnswerRecord`：`user_id / question_id(FK CASCADE) / user_answer / is_correct / spent_seconds / created_at` —— **不涉及知识点**
- `WrongBookItem`：`user_id / question_id(FK CASCADE) / mistake_reason / review_* 字段` + `question` relationship —— **不涉及知识点**，但错题复习通过 `question.knowledge_point` 间接触达知识点
- `KnowledgePoint`（`backend/app/models/knowledge.py`）：全局共享表，`uq_knowledge_points_normalized_subject_name` 唯一约束，`parent_id` 自引用 FK `RESTRICT`，`status/source` 带 server_default

`_save_questions()`（`api/routes/questions.py`）是题目唯一写入点：AI 出题后落库，`knowledge_point` 直接取请求/AI 返回的自由文本。

---

## 2. `questions.knowledge_point` 真实使用情况

**结论：纯自由文本字段，无任何约束、无索引、无 FK，读写点共 7 处。**

| 位置 | 读写 | 用途 |
|---|---|---|
| `api/routes/questions.py` `_save_questions` | 写 | AI 出题落库 |
| `api/routes/questions.py` `generate`（reference 分支） | 读 | 变体题生成时回传原题知识点 |
| `services/question_generator.py` | 读/写 | AI prompt 与结果归一化（`_normalize` 会回填请求值） |
| `services/pet_ai.py` L79 | 读 | 宠物对话收集错题薄弱知识点（自由文本列表） |
| `services/plan_chat.py` L211 | 读 | 学习计划对话收集薄弱知识点（自由文本列表） |
| `schemas/question.py` `QuestionOut/QuestionGenerateRequest` | 序列化/入参 | API 契约 |
| `schemas/admin.py` L75 | 序列化 | 管理端题目只读视图 |

### 关键回答

- **是自由文本吗？** 是。`String(200)` NOT NULL，无约束。前端出题表单默认值就是「数据结构 / 栈和队列」，生产 8 条数据全部来自该默认值。
- **AI 出题是否直接写这个字段？** 是，`_save_questions` 直接写，不经过任何知识点解析。
- **前端是否依赖？** 是（见第 4 节）。
- **是否有按该字段查询的代码？** 无任何 SQL/ORM 按该字段过滤；pet_ai / plan_chat 只做内存内去重收集，不做 DB 查询。

---

## 3. 生产数据统计（2026-10-01，只读查询 ai-study-mysql）

| 指标 | 值 |
|---|---|
| questions 总数 | **8** |
| knowledge_point NULL | 0 |
| knowledge_point 空字符串 | 0 |
| distinct knowledge_point | **1**（`栈和队列`） |
| subject 分布 | 全部 `数据结构` |
| source 分布 | 全部 `ai` |
| knowledge_points 表行数 | **0（空表）** |

### A/B/C/D 分类结果

| 类别 | 定义 | 结果 |
|---|---|---|
| A 可唯一匹配现有知识点 | normalized_subject + normalized_name 精确命中 | **0 条**（kp 表为空，无从匹配） |
| B 无匹配 | — | **8 条**（全部为 数据结构/栈和队列） |
| C 多义/冲突 | 同一 normalized 对多个 KP | 0 条 |
| D 空值 | NULL/空串 | 0 条 |

**注意**：这 8 条的前端出题表单默认值是「数据结构 / 栈和队列」（`web/src/views/QuestionsView.vue` L10-11），基本可判定为早期冒烟/演示数据，非真实用户学习数据。

### Backfill 影响评估

- 第一轮 migration 做 deterministic backfill（仅精确匹配）→ **实际回填 0 行**。
- **不自动创建** `栈和队列` KnowledgePoint（遵守"不要因为旧字符串无法匹配就擅自生成新知识点"）。
- 8 条记录全部进入**待处理清单**：若后续管理员在「数据结构」下手工创建 `栈和队列`，可通过幂等 backfill 脚本或管理端 attach 一键补齐；若判定为垃圾数据，也可随题目清理。
- 旧字段**保留不删**，`QuestionOut` 继续输出，展示兼容零破坏。

---

## 4. 现有 API / Service / AI / 前端依赖

### 后端 API

- `POST /questions/generate`：入参 `knowledge_point`（自由文本），出题→落库→返回。
- `GET /questions`、`PATCH /questions/{id}/favorite`、`DELETE /questions/{id}`（手动清理 AnswerRecord/WrongBookItem 后删题）。
- `GET /wrong-book`、`GET /wrong-book/review`、`PATCH /wrong-book/{id}`：嵌套返回 `question`（含 knowledge_point 文本）。
- `KnowledgePointService`（Phase 1，332 行）：标准化（`clean_name` 折叠空白+小写、`normalize_subject`）、学科内唯一、parent 同学科、禁自引用、禁环、有 children 禁删、普通用户只读/管理员可写。**当前没有任何 question 关联逻辑。**

### Web 前端（6 处）

| 文件 | 依赖方式 |
|---|---|
| `QuestionsView.vue` | 出题表单输入知识点（自由文本，默认「栈和队列」） |
| `WrongBookView.vue` | 基于错题的 `question.knowledge_point` 再生成同类题 + 文案展示 |
| `AdminQuestionsView.vue` | 只读展示 `item.knowledge_point` |
| `api/questions.ts` | `QuestionGeneratePayload.knowledge_point` |
| `types/index.ts` | `Question.knowledge_point` 类型定义 |
| `FilesView.vue` / `api/files.ts` | `knowledge_points` 是**数字**（文件分析返回的出题知识点数量），与本题无关，勿混淆 |

### 移动端（3 处）

`mobile/src/pages/questions/questions.vue`、`wrong-book.vue`、`types/index.ts`：与 Web 同模式（表单输入 + 展示），无额外查询依赖。

### 测试现状

`test_questions.py`、`test_question_variety.py`、`test_knowledge_points.py`、`test_wrong_book_review.py`、`test_schema_tools.py`。均基于旧字段契约，Phase 2 新增测试不应破坏现有断言。

---

## 5. 推荐数据模型：`question_knowledge_points`

**采用独立关联表（Many-to-Many），带代理主键** —— 与项目现有风格一致（所有表均用 `id` 代理主键 + `created_at`，无联合主键先例）：

```
question_knowledge_points
├── id                INT PK AUTO_INCREMENT
├── question_id       INT FK → questions.id        ON DELETE CASCADE, INDEX
├── knowledge_point_id INT FK → knowledge_points.id ON DELETE RESTRICT(见 §7), INDEX
├── role              VARCHAR(16)  NOT NULL DEFAULT 'primary'   # primary | secondary
├── source            VARCHAR(16)  NOT NULL DEFAULT 'manual'    # manual | ai | legacy | system
├── created_at        DATETIME server_default now()
└── UNIQUE (question_id, knowledge_point_id)          uq_question_knowledge_points_pair
```

**不用简单 `questions.knowledge_point_id`**：文档明确要求支持多知识点、主次区分、Phase 3 按关联计算掌握度——单列 FK 无法承载。

---

## 6. role / source / weight 是否需要

| 字段 | 结论 | 理由 |
|---|---|---|
| `role` | **需要** | 文档目标明确要求区分主要/次要知识点；Phase 3 掌握度主次加权会用到。默认 `primary`；DB 层不强制"每题最多一个 primary"（MySQL 无 partial unique），由 Service 层保证（replace/set_primary 语义内自洽） |
| `source` | **需要（低成本）** | 用于区分 legacy backfill / AI resolver / 人工设置，是 Phase 2 迁移策略本身的自证字段；4 个枚举值已在文档定义，无过度设计 |
| `weight` | **不需要，本轮不加** | 当前无任何业务方消费权重数值；Phase 3 若真需要，届时加列即可（新表加列是普通 migration，成本极低）。避免文档警告的"为未来想象过度设计" |

---

## 7. FK / Unique / Cascade 策略

| 约束 | 设计 | 理由 |
|---|---|---|
| `question_id` FK | `ON DELETE CASCADE` | 与 `AnswerRecord`/`WrongBookItem` 现有模式一致；用户删题时关联无独立存在意义。现有删题路由已手动清理两张表，新表靠 DB 级联即可（也可选择在路由中显式删除，实现阶段二选一） |
| `knowledge_point_id` FK | `ON DELETE RESTRICT` + Service 层预检 | **不破坏 Phase 1 规则**：在 `KnowledgePointService.delete` 中新增预检——有关联题目时抛新异常（如 `KnowledgePointInUse`），管理员须先 detach 或走显式确认。RESTRICT 兜底防 DB 层意外级联 |
| 唯一约束 | `UNIQUE(question_id, knowledge_point_id)` | 同题同知识点不可重复；attach 重复时 Service 捕获 IntegityError 转为幂等成功或 409（见 §11 测试口径） |
| 索引 | `question_id`、`knowledge_point_id` 各建普通索引 | 双向查询（题→点、点→题）都要走索引 |

---

## 8. Subject Consistency 策略

**推荐：attach/replace 时强制一致**——`normalize_subject(Question.subject) == knowledge_point.normalized_subject`，否则 400（`subject 不一致`）。

依据：

- Phase 1 已建立"知识点归属学科"的模型，题目也带 subject；跨学科关联会让 Phase 3 掌握度统计口径混乱。
- `normalize_subject` 已存在（清洗空白+lower），比较成本低。
- 生产 8 条数据无跨学科冲突，无存量矛盾需要消化。
- 不做 subject 的模糊/同义词匹配（如「高数」vs「高等数学」）——这属于未来的知识点治理，Phase 2 不碰。

**不做**双向自动同步（改题 subject 时不自动清理不一致关联）；实现时在"题目 subject 不可变"前提下此问题不存在（当前确实没有改 subject 的 API）。

---

## 9. Legacy Backfill 策略（第一轮 migration 内容）

1. `op.create_table(...)` 建关联表（唯一 DDL）。
2. Deterministic backfill：`INSERT ... SELECT` 仅回填 `LOWER(TRIM(q.subject)) = kp.normalized_subject AND LOWER(TRIM(q.knowledge_point)) = kp.normalized_name` 的行（与 `clean_name/clean_subject` 的空白折叠+小写语义对齐；中文场景等价于精确匹配），`role='primary', source='legacy'`。
3. **实际效果（本次生产数据）：回填 0 行，8 条进待处理清单**——kp 表为空，无任何匹配可能。
4. 旧字段 `questions.knowledge_point` **原样保留**，不删列、不改 nullable、不动任何历史 migration。
5. 不自动创建任何 KnowledgePoint。

待处理清单交付形式：migration 执行后由审计脚本/SQL 输出未匹配 `(subject, knowledge_point)` distinct 清单（当前就是 1 行：数据结构/栈和队列 × 8 题），供管理员决策（建知识点后补挂 vs 忽略）。

---

## 10. API 设计（草案）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| `GET` | `/questions/{question_id}/knowledge-points` | 题目 owner 或管理员 | 返回关联知识点列表（含 role/source） |
| `PUT` | `/questions/{question_id}/knowledge-points` | 题目 owner 或管理员 | `replace`：全量替换，body 为 `[{knowledge_point_id, role}]`（≤1 个 primary） |
| `POST` | `/questions/{question_id}/knowledge-points` | 同上 | `attach` 单个 |
| `DELETE` | `/questions/{question_id}/knowledge-points/{kp_id}` | 同上 | `detach` |
| `PATCH` | `/questions/{question_id}/knowledge-points/{kp_id}` | 同上 | `set_primary` |
| `GET` | `/knowledge-points/{kp_id}/questions` | **仅管理员**（或强制 `?mine=true` 按 owner 过滤） | ⚠️ 题目是用户私有数据，全局反查会泄漏他人题目——普通用户反查必须限定本人题目 |

- **权限结论**：题目↔知识点关联挂在**用户自己的题目**上，沿袭现有"用户可管理自己题目"模型（可删题、可收藏），owner 可写；但**全局知识点本身**的创建/修改仍仅管理员（Phase 1 规则不动）。普通用户不能把关联挂到别人题目上（owner 校验天然拦截）。
- **批量关联能力**：本轮不做独立 bulk 端点；`replace` 一次提交多对已覆盖主要场景，AI resolver 批量解析留给后续接口（§11）。

---

## 11. Service 设计

新建 `backend/app/services/question_knowledge_point_service.py`，风格对齐 `KnowledgePointService`（Service 持 db，自定义异常，Router 薄封装）：

```
QuestionKnowledgePointService
├── list_for_question(question_id, owner_id) -> list[Association]
├── list_question_ids_for_knowledge_point(kp_id, owner_id|None) -> list[int]
├── attach(question_id, kp_id, role, source, owner_id) -> Association
├── detach(question_id, kp_id, owner_id) -> None
├── replace(question_id, items, source, owner_id) -> list[Association]
├── set_primary(question_id, kp_id, owner_id) -> Association
└── bulk_resolve(texts, subject) -> ResolveReport        # AI resolver 预留接口，本轮仅签名+NotImplemented 或最小实现
```

必须处理的错误（映射 HTTP）：

- `QuestionNotFound` → 404（含 owner 校验，越权一律 404）
- `KnowledgePointNotFound` → 404
- `SubjectMismatch` → 400
- duplicate attach → **幂等成功**（返回既有关联；`replace` 内部按 set 语义去重）——比 409 对前端更友好，测试两种口径之一即可，实现时固定
- `PrimaryConflict`（replace 含多个 primary）→ 400
- detach 导致题目失去全部关联 → 允许（关联是增强信息，不强约束题目必有知识点）

**AI 出题兼容**（§九要求）：`generate` 请求体新增**可选** `knowledge_point_id`；传入时走 `QuestionKnowledgePointService.attach(source='manual')`，不传时行为完全不变（AI 继续写自由文本旧字段）。禁止任何代码绕过 Service 直写关联表。`KnowledgePointResolver`（自由文本→kp_id）只定接口不实现，供后续 AI 出题升级。

---

## 12. Alembic Migration 设计

- 新文件：`backend/alembic/versions/20261001_001_add_question_knowledge_points.py`
- `revision = "20261001_001"`，`down_revision = "20260909_001"`（已确认现行 head 标识符，勿改历史文件）
- `upgrade()`：create_table + 两个 FK + unique + 两个 index + deterministic backfill INSERT...SELECT
- `downgrade()`：drop_table（关联表无历史包袱，可安全回滚）
- **配套必改**（Stage 3 治理产物，不改会 fail-closed）：
  - `app/core/schema_profiles.json`：由 `backend/tests/freeze_schema_profiles.py` 重新冻结（MySQL fresh / SQLite fresh / 生产三份 profile 都含新表）
  - `app/core/schema_reconciliation_manifest.py`：如新表列带 server_default（created_at），按现有 manifest 惯例登记条目（对齐 `knowledge_points.status/source` 的做法）
- 验收门槛（全部通过才可部署）：Fresh MySQL 8.4 全量升级 ✅ / Fresh SQLite 全量升级 ✅ / 生产 `alembic upgrade head` 为增量 no-impact ✅ / `alembic check` ✅ / Drift Checker errors=0 ✅ / 新 Schema 指纹记录归档 ✅
- 部署沿用已建成的 migration-first 流程（`production_release.sh`，EXPECTED_COMMIT 锁定）

---

## 13. 测试计划

新增 `backend/tests/test_question_knowledge_points.py`：

1. attach 成功（含 role/source 默认值）
2. duplicate attach → 幂等（不产生第二行）
3. detach 成功；detach 不存在关联 → 404
4. replace 全量替换（含 primary 唯一性校验、多 primary 400）
5. question 不存在 / 越权他人题目 → 404
6. knowledge point 不存在 → 404
7. subject 不一致 → 400
8. set_primary 成功且旧 primary 被降级为 secondary
9. 多知识点题目（primary + secondary 共存）
10. 一个知识点关联多题
11. API 权限：普通用户不能写别人题目；普通用户不可写全局知识点（Phase 1 回归）
12. legacy backfill：构造 `questions.knowledge_point` 文本与既有 kp 精确匹配 → 回填 source=legacy；无匹配 → **不创建 KP、不回填、旧字段原样**
13. migration upgrade：fresh MySQL/SQLite 跑全量后新表存在、约束生效
14. schema drift：Drift Checker errors=0；schema_profiles 已重冻结
15. 回归：现有 test_questions / test_wrong_book_review / test_knowledge_points 全绿（旧字段契约不变）

---

## 14. 与 Phase 3 的接口边界

- Phase 3（掌握度）将**只读消费**本关联表：按 `(user_id → wrong_book/answer_records → question_id → kp_id, role)` 聚合，role 用于主次加权；本轮落库的 `source` 也为其区分"AI 关联 vs 人工确认"保留口径。
- 本轮**不做**任何聚合表、掌握度字段、缓存、定时任务；不动 AnswerRecord/WrongBookItem 结构。
- pet_ai / plan_chat 当前读 `question.knowledge_point` 自由文本——Phase 2 保持不动（兼容读取）；Phase 3+ 可平滑切换为读结构化关联（读取端改动，无迁移风险）。

---

## 15. 风险清单

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | Schema 指纹变化（095bf987 → 新值），Stage 3 门禁体系会感知 | 中 | 按既定流程重冻结 profiles + 更新 manifest，production_release.sh 门禁自然放行；指纹变更记录归档 |
| R2 | `GET /knowledge-points/{id}/questions` 泄漏他人题目 | 中 | 设计已限定管理员/或强制 owner 过滤；实现时加测试 |
| R3 | legacy backfill 匹配语义与 Python `clean_name`（全角空白折叠）不完全一致 | 低 | 当前生产 0 匹配、数据量 8 行，SQL 用 LOWER(TRIM()) 已覆盖现网实况；全角空白类脏值进待处理清单人工处理 |
| R4 | "每题最多一个 primary" 仅 Service 层保证，直写 DB 可绕过 | 低 | 本项目无直写 DB 路径；如需硬保证可在 MySQL 加生成列唯一索引（本轮不做，避免过度设计） |
| R5 | 前端仍以自由文本出题，双轨并存期数据不一致（有文本无关联） | 低 | 属预期状态：结构化关联是增量能力；后续 Phase 再做前端出题时选择知识点 + AI resolver |
| R6 | 删题路径漏清关联 | 低 | FK CASCADE 兜底 + 路由显式清理二选一（实现时定），加测试 |
| R7 | 本轮新增表使 `create_all`（测试环境）与 Alembic 双源差异 | 低 | 新模型注册进 `models/__init__` 后两侧自然一致；schema 测试覆盖 |

---

## 16. 预计修改文件

**实现阶段（确认设计后）预计触达：**

| 文件 | 动作 |
|---|---|
| `backend/app/models/learning.py`（或新建 `models/question_knowledge.py`，实现时按项目聚合风格定） | 新增 `QuestionKnowledgePoint` ORM |
| `backend/app/models/__init__.py` | 导出新模型 |
| `backend/app/services/question_knowledge_point_service.py` | **新建** Service |
| `backend/app/services/knowledge_point_service.py` | `delete()` 新增关联使用预检（新增异常类） |
| `backend/app/schemas/question.py` / `schemas/knowledge.py` | 新增关联 Read/Attach/Replace Schema；`QuestionGenerateRequest` 可选 `knowledge_point_id` |
| `backend/app/api/routes/questions.py` | 关联 4~5 个端点 + generate 可选挂载 |
| `backend/app/api/routes/knowledge_points.py` | 反查端点（管理员/owner 过滤） |
| `backend/alembic/versions/20261001_001_add_question_knowledge_points.py` | **新建** migration |
| `backend/app/core/schema_profiles.json` | `freeze_schema_profiles.py` 重新冻结 |
| `backend/app/core/schema_reconciliation_manifest.py` | 新表 server_default 登记（如需） |
| `backend/tests/test_question_knowledge_points.py` | **新建** 测试 |
| （可选）`backend/tests/conftest.py` | fixture 补充 |

**明确不修改**：`questions.knowledge_point` 列、历史 migration、`question_generator.py` prompt 逻辑、Web/Mobile 前端（展示层可后续独立迭代）、pet_ai / plan_chat。

---

## 结论与请求确认

现有基础比文档预估更简单：**生产仅 8 条演示性质的题目数据、knowledge_points 表为空、旧字段无任何查询依赖**——Phase 2 的迁移风险接近下限，backfill 实际为"建表 + 零回填 + 8 条待处理清单"。

核心设计决策待确认：

1. 关联表采用**代理主键 + UNIQUE(question_id, knowledge_point_id)**，含 `role`/`source`，**不含 `weight`** —— 是否同意？
2. `knowledge_point_id` FK 用 **RESTRICT + Service 删除预检（有关联禁删）** —— 是否同意？（备选：CASCADE 静默清理）
3. Subject 一致性**强制校验**（attach/replace 时 400）—— 是否同意？
4. duplicate attach 语义选**幂等成功**而非 409 —— 是否同意？
5. API 权限：owner 可管理自己题目的关联；KP 反查题目仅管理员/限本人 —— 是否同意？
6. 本轮前端不做 UI 改动（双轨兼容：旧字段继续展示，关联表暂无界面）—— 是否同意？

确认后进入实现（按新节奏：实现 → 测试 → 部署）。
