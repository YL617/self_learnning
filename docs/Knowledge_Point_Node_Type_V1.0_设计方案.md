# Knowledge Point Node Type V1.0 技术方案

> 状态：**只读架构审计 + 技术方案（未落地）**
> 本轮约束：❌ 不修改代码　❌ 不创建 migration　❌ 不部署　❌ 不 commit
> 产出：架构分析 + 技术方案，等待确认后进入实施阶段
> 关联文档：《知识节点类型技术审计报告.md》（结论一致，本文为其「可执行落地版」）
> 审计基线：生产 HEAD `e8a5151`，alembic `20261001_004`，`knowledge_points` 生产 **0 行**

---

## 0. 结论先行（TL;DR）

| 项目 | 结论 |
|---|---|
| **P0 判定** | ✅ 确认存在。`KnowledgePoint` **没有任何字段**表达节点类型，container 与 concept 完全同质 |
| **推荐方案** | **方案 A：新增 `node_type VARCHAR(16) NOT NULL DEFAULT 'concept'` + CHECK + INDEX** |
| **明确否决** | 方案 B `is_learnable`（布尔无法扩展、把能力与身份混同）；方案 C 靠 `code/difficulty/estimated_minutes IS NULL` 推断（4 处硬伤，见 §2.1.3） |
| **迁移风险** | **极低**：生产 0 行 → `ADD COLUMN` 对线上是空操作；`NOT NULL + server_default` 对未来大数据量免回填 |
| **回归面** | 后端 12 处 + 前端 4 处为 **A 必须修改**；另有 10 处 B 建议、6 处 C 暂不改（§1.2 全量清单，不遗漏） |
| **预计工作量** | **约 1.5 ～ 2.5 人日**（含后端 + 导入 + 前端 + 测试 + migration，不含视觉细调） |
| **不可逆性** | 低。`downgrade` 只删除本 revision 新增的对象，无数据丢失 |

---

# 第一阶段：只读架构审计

## 1.1 当前 `knowledge_points` 数据模型完整分析

来源：`backend/app/models/knowledge.py:123-193`（ORM）+ `backend/alembic/versions/20260908_add_knowledge_points.py` / `20261001_004_*.py`（schema）+ `20261001_001/002/003`（关联表）。

### 1.1.1 主表 `knowledge_points`

| # | 字段 | 类型 | 作用 | 是否受 `node_type` 影响 |
|---|---|---|---|---|
| 1 | `id` | `INT PK, index` | 主键；被 4 张关联表以外键引用 | 否 |
| 2 | `name` | `VARCHAR(200) NOT NULL` | 展示名 | 否 |
| 3 | `normalized_name` | `VARCHAR(200) NOT NULL` | 归一化去重键（小写+折叠空白） | **是**（构成唯一键的一半，见 §1.1.2） |
| 4 | `subject` | `VARCHAR(100) NOT NULL` | 学科展示名 | 否 |
| 5 | `normalized_subject` | `VARCHAR(100) NOT NULL` | 学科去重键 | **是**（同上） |
| 6 | `parent_id` | `INT FK→self ON DELETE RESTRICT, index, NULL` | **part-of 层级**（树、单父） | **是**（container 才应做父；语义需收紧） |
| 7 | `description` | `TEXT NULL` | 描述 | 否 |
| 8 | `status` | `VARCHAR(16) DEFAULT 'active'` | `active/pending/disabled` | **是**（当前是唯一的过滤维度，见 §1.2-A7） |
| 9 | `source` | `VARCHAR(16) DEFAULT 'system'` | `system/admin/ai`（**只表来源，不表类型**） | **是**（易被误当成类型位，见 §1.1.3） |
| 10 | `code` | `VARCHAR(64) NULL, UNIQUE` | 稳定知识资产 ID | **是**（容器当前普遍为 NULL → 曾被当作推断依据，已否决） |
| 11 | `aliases` | `JSON NULL` | 同义名数组；M4 AI 标注召回词表 | **是**（容器不该进词表） |
| 12 | `difficulty` | `VARCHAR(16) NULL` + CHECK `easy/medium/hard` | 展示/排序/推荐；**不参与 mastery** | **是**（仅 concept 有意义） |
| 13 | `estimated_minutes` | `INT NULL` + CHECK `>= 0` | 预估时长 | **是**（仅 concept 有意义） |
| 14 | `import_batch_id` | `INT FK→knowledge_point_import_batches ON DELETE SET NULL, index, NULL` | 批次追溯/回滚 | **是**（container 与 concept 同批次产生，无法区分） |
| 15 | `created_at` | `DATETIME server_default now()` | 审计 | 否 |
| 16 | `updated_at` | `DATETIME server_default now() onupdate now()` | 审计 | 否 |
| 17 | `parent` / `children` | relationship（`remote_side=[id]`） | ORM 树导航 | **是**（container 才应做父） |

### 1.1.2 约束

| 约束 | 定义 | 与 `node_type` 的关系 |
|---|---|---|
| `uq_knowledge_points_normalized_subject_name` | `UNIQUE(normalized_subject, normalized_name)` | **关键副作用**：container 与 concept **共用同一命名空间**。容器占名后，该名字永久不能用于真知识点。V1.1 真实踩到：`栈/队列/串/图/查找/排序/线性表/二叉树` 8 个名字被容器占用 |
| `uq_knowledge_points_code` | `UNIQUE(code)` | 容器 `code` 一般为 NULL；两库 UNIQUE 允许多 NULL，故容器可共存 |
| `ck_knowledge_points_difficulty` | `difficulty IS NULL OR difficulty IN (...)` | 已有词表约束范式 → 本方案的 `ck_knowledge_points_node_type` 可直接照抄此模式 |
| `ck_knowledge_points_estimated_minutes` | `estimated_minutes IS NULL OR >= 0` | 同上 |

### 1.1.3 关联表（4 张，全部以 `knowledge_points.id` 为端点）

| 表 | 端点 | 语义 | container 混入的后果 |
|---|---|---|---|
| `question_knowledge_points`（`20261001_001`） | `question_id` × `knowledge_point_id`，含 `role ∈ {primary, secondary}`、`UNIQUE(question_id, knowledge_point_id)` | 题目↔知识点 | 容器可被关联 → 容器进 mastery 链 |
| `user_knowledge_point_mastery`（`20261001_002`） | `(user_id, knowledge_point_id)` | 掌握度 | **容器会产生 mastery 行** → 掌握度统计污染 |
| `knowledge_point_prerequisites`（`20261001_003`） | `(knowledge_point_id, prerequisite_id)` + `strength` + `CHECK no_self_loop` | 前置依赖 DAG | 容器可作前置边端点 → 学习路径指向目录 |
| `knowledge_point_import_batches`（`20261001_004`） | 被 `import_batch_id` 引用 | 批次追溯/回滚 | 无（批次本身中立） |

### 1.1.4 `source` 为什么不能当类型位（重要）

M2 导入时，自动创建的父节点与真实行**都**写 `source = KP_SOURCE_ADMIN`（`knowledge_import.py:1178-1185`），`status` 也都写 `active`，`import_batch_id` 也相同。即：**当前没有任何一个已存字段能把二者分开**。这就是 P0。

---

## 1.2 影响范围分析（逐项，A/B/C 分类，不遗漏）

> 检索方式：`grep -r "KnowledgePoint" backend/app` → 21 文件；逐处读上下文判定。
> A = 必须修改（不改就有正确性缺陷 / 用户明确要求）；B = 建议修改（语义/体验不完整）；C = 暂不修改（记录理由）。

### A. 必须修改（12 处）

| # | 文件:位置 | 现状 | 为什么必须改 | 改法 |
|---|---|---|---|---|
| **A1** | `models/knowledge.py:123-193` | 无类型列 | 方案根 | 加 `node_type` 列 + CHECK |
| **A2** | `alembic/versions/`（新增） | — | 方案根 | 新 revision（§2.2） |
| **A3** | `schemas/knowledge.py` `KnowledgePointCreate/Update/Read` | 无 `node_type` | API 需要能设置/读回 | 加 `node_type: Literal["container","concept"]`，Create 默认 `concept` |
| **A4** | `services/knowledge_point_service.py:99-117` `list_all()` | 只有 `subject/parent_id/query` 过滤 | 前端 selector 需要「只 concept」的服务端过滤 | 加 `node_type: str\|None` 参数 |
| **A5** | `services/knowledge_point_service.py:246-284` `create()` | 无 `node_type` 参数 | 导入链路依赖它写入类型 | 加参数 + `_assert_node_type()` |
| **A6** | `services/recommendation.py:363-367` `_knowledge_points()` | **只** `status == "active"` | **推荐会把 container 当候选**（4 个动作全部受影响） | `+ KnowledgePoint.node_type == "concept"` |
| **A7** | `services/recommendation.py:169-200` `data_scale()` | `count(KnowledgePoint.id)` 全表 | `knowledge_point_count` 是**数据规模快照（门禁透明度用）**的组成部分；含容器会让**快照口径失真** | `+ where(node_type == "concept")` |
| **A8** | `services/prerequisite_suggest.py:36-48` `_candidates()` | **只** `status == "active"` | **LLM 会把 container 当候选**并提议为前置 | `+ node_type == "concept"` |
| **A9** | `services/question_knowledge_point_service.py:66-70` `_get_knowledge_point()` | 只判存在 | **容器可被题目关联 → 直接污染 mastery**。这是「容器不产生 mastery」的**唯一可靠关口** | 若 `node_type == "container"` → raise（新异常 `NotLearnableNode`） |
| **A10** | `services/knowledge_import.py:1077-1104 / 1161-1188` `_creation_specs()` + `ensure()` | auto-parent 与真实行**同质**创建 | **新数据从源头就正确**，否则 AI 标注/推荐继续被污染 | auto-parent → `node_type='container'`；`plan.rows` 的 create → `'concept'`（§2.4） |
| **A11** | `api/routes/knowledge_points.py:63-71` `list_knowledge_points` | 无 `node_type` query | 前端过滤必须走后端（不能只在前端过滤，否则分页/权限会漏） | 加 `node_type: str \| None = Query(None)` |
| **A12** | 前端 4 处：`KnowledgePointSelector.vue:62`、`PrerequisiteEditor.vue:46`、`QuestionKnowledgePointsModal.vue:53`、`AdminKnowledgePointsView.vue`（表格+表单） | 全部无类型概念 | 用户明确要求：「selector 默认只 concept」「前置编辑只 concept」「admin 显示 📁/🧠」 | §2.5 |

> **[口径修正 · 重要]** 读代码核实后修正一处易错认知：
> - `DataScaleSnapshot.kp_coverage` 的定义是 **`tagged_question_count / question_count`**（`recommendation.py:135-139`），**与 `knowledge_point_count` 无关**。
> - `knowledge_point_count` **当前只用于「规模快照」的展示/透明度**，`check_bkt_gate()` 与 `check_deep_kt_gate()` 的公式**都没有直接吃这个值**（`check_bkt_gate` 用 `total_answers` / `median_kp_answers` / `user_count` / `kp_coverage`）。
> - 因此 A7 的性质是 **「快照/报告口径失真」**（中低严重度），**不是**「门禁被直接污染」。
> - 而 `kp_coverage` 的真实污染路径是：**某道题被关联到 container** → 该题仍计入 `tagged_question_count` → 覆盖率虚高。这条路径**由 A9（题目关联关口）兜住**。

### B. 建议修改（10 处）

| # | 文件:位置 | 现状 | 为什么建议改 | 改法 |
|---|---|---|---|---|
| B1 | `services/recommendation.py:428-436` `_legacy_index()` | 全量建 `(subject,name)` 索引 | legacy 题目文本回退解析可能命中容器名 | 只索引 concept（1 行 where） |
| B2 | `services/recommendation.py:601-614` `_question_primary_kp_map()` | 只按 role 过滤 | 若历史存在容器关联，展示会带容器名 | join 后加 `node_type == "concept"` |
| B3 | `services/prerequisite.py:297-338` `_assert_exists()` / `add()` | 只判 id 存在 | 应从服务层拒绝 container 作前置端点（DB 无法表达，因 FK 指向同表） | `add()` 校验两端 `node_type=='concept'` |
| B4 | `api/routes/knowledge_points.py:242-294` `add_prerequisite` / `suggest` | 无类型校验 | 同上，API 层给明确 400 而非 500 | 依赖 B3 |
| B5 | `services/mastery.py:151-172` `list_weak()` | 无类型过滤 | 防御历史脏数据（若曾有容器 mastery 行） | join concept 过滤（可选，成本 1 行） |
| B6 | `api/routes/mastery.py:51-82` `summary` | `total` / `weak_count` / `average_score` 全量 | 同上，避免「总数虚高」 | 依赖 B5 或在此 join |
| B7 | `api/routes/knowledge_points.py:162-178` `delete` 预检 | 已拦 children/题目/前置/mastery | 建议再加「container 删除前提示其子节点」的友好文案 | 文案层 |
| B8 | 前端 `utils/knowledgePoints.ts` `buildRows/parentCandidates` | 无类型概念 | 表格要显示类型徽标；父候选允许 container 但需标注 | 加 `nodeType` 字段与展示 |
| B9 | 前端 `AdminKnowledgeImportView.vue` + `KnowledgeImportPreviewTable.vue` | 预览无类型列 | **让管理员在写库前看到「将创建为 container 的行」**（防错核心） | 预览增加「类型」列 |
| B10 | 前端 `api/knowledgePoints.ts` + `types/index.ts` | 无 `node_type` | 类型安全 | 加字段 + 参数 |

### C. 暂不修改（6 处，记录理由）

| # | 文件:位置 | 为什么暂不改 |
|---|---|---|
| C1 | `services/mastery.py:207-236` `apply_evaluation()` | 掌握度写入的输入是 `EvaluationResult` 的 signal；**只要 A9 关住关联关，容器永远不会出现在 signal 里**。在此加判断是重复防御，且会让 mastery 模块知道「节点类型」这个新概念（越界） |
| C2 | `services/prerequisite.py` 全部图算法（`topological_order` / `closure` / `unlock_count`） | 纯图算法，只吃 `(dependent, prerequisite)` 边集；只要 B3 保证边端点都是 concept，算法本身无需知晓 node_type |
| C3 | `services/knowledge_point_service.py:224-244` `_assert_parent()` / `_assert_no_cycle()` | 「container 作父」是**允许**的（§2.3），现有逻辑天然正确，无需改 |
| C4 | `services/knowledge_import.py:1302-1371` `collect_blockers()` | 回滚预检只看关联引用，与类型无关 |
| C5 | 前端知识树组件（admin 知识点页的树视图） | 用户明确要求「知识树允许显示全部」，保持现状 |
| C6 | `services/study_planner.py` / `plan_chat.py` / `rag.py` / `course_recommender.py` | 已确认**不直接查询** `KnowledgePoint`（grep 无命中）；它们通过 `learning_state_context()` 间接消费，而该函数的数据源是 mastery 表 → 被 A9/A6 上游覆盖 |

### D. 「设计约束」——尚未实现但必须写进契约（2 处）

| # | 位置 | 内容 |
|---|---|---|
| D1 | **M4 AI 自动标注**（`docs/大阶段4实施设计方案.md` §241-243） | 设计明确写「词表 = 同 subject 下所有知识点的 name + aliases + code」。**必须改为 `node_type='concept'` 的子集**，否则「树」「排序」等目录名会命中题干，容器被标为知识点。**这是 P0 不修时最先爆的地方** |
| D2 | **M6 质量系统 K1/K2** | K1「孤立知识点」/K2「覆盖率」若把 container 计入分母，覆盖率会虚高 → 直接影响 V2 门禁判定 |

### A/B/C 数量小结

```
A 必须修改   12 处（后端 8 + 前端 4）
B 建议修改   10 处（后端 6 + 前端 4）
C 暂不修改    6 处
D 设计约束    2 处（M4 / M6）
--------------------------------
合计         30 处
```

---

# 第二阶段：方案设计

## 2.1 数据模型设计

### 2.1.1 推荐：`node_type`

```python
# app/models/knowledge.py :: KnowledgePoint
node_type: Mapped[str] = mapped_column(
    String(16), nullable=False, default="concept", server_default="concept"
)
```

```python
__table_args__ = (
    # ... 既有约束 ...
    CheckConstraint(
        "node_type IN ('container', 'concept')",
        name="ck_knowledge_points_node_type",
    ),
)
```

**第一版只允许两个值**：

| 值 | 中文 | 含义 | 例 |
|---|---|---|---|
| `container` | 目录节点 | **纯组织结构**，不承载学习行为 | 数据结构、树与二叉树、排序、图、最小生成树 |
| `concept` | 可学习知识点 | **可教学、可测试、可度量**的原子能力 | DFS、BFS、快速排序、Dijkstra 算法 |

**为什么只两个值（不预留 group/skill/standard 等）**：CASE 1.1 的经验是「类型词表要小而稳，随真实需求扩展」。当前系统只存在这两种真实语义，预留空类型会让每个 `if` 分支都要考虑不存在的值。扩展成本很低（改 CHECK + 加一个枚举值），不需要预留。

### 2.1.2 为什么**不用** `is_learnable`（布尔）

| 维度 | `is_learnable: bool` | `node_type: enum` |
|---|---|---|
| **表达能力** | 2 个状态，只能表达「能/不能学」 | n 个状态，能表达「它**是什么**」 |
| **语义层次** | 描述 **capability**（能力），而 capability 会随需求变（可出题？可推荐？可作前置？） | 描述 **identity**（身份），身份稳定 |
| **组合爆炸** | 一旦出现第三种节点（如未来的「试卷结构节点」「能力项」），要么塞进 `False` 桶，要么再加 `is_assessable` / `is_recommendable` → N 个布尔交叉出 2^N 个无效组合 | 加一个枚举值即可，无交叉 |
| **迁移代价** | 从 bool → enum 是一次**列替换 + 全量回填 + 改所有分支** | 从 2 值 → 3 值只是改 CHECK |
| **CASE 1.1 佐证** | 官方明确建议**不同层级/不同角色用不同 `CFItemType`**，而不是一个布尔开关 | 与本方案一致 |
| **空值语义** | `False` 有歧义：「它是目录」还是「它还没被判定」？ | `container` 无歧义 |
| **可读性** | `if not kp.is_learnable:`（否定式，易错） | `if kp.node_type == "container":`（直白） |

**结论**：`is_learnable` 把「身份」压缩成「能力开关」，是一个会把未来复杂度藏进布尔代价里的设计。

### 2.1.3 为什么**不用**「通过 NULL 字段推断」（方案 C）

候选判据曾是「`code IS NULL AND difficulty IS NULL AND estimated_minutes IS NULL` → 是容器」。**四处硬伤，逐一否决**：

| # | 硬伤 | 反例 |
|---|---|---|
| **C-1** | **容器可以有 `aliases`** | 「树」容器完全可以填别名 `树形结构`；V1.1 的 22 个容器中有多个可填别名 → `aliases IS NULL` 不成立 |
| **C-2** | **合法 concept 也可以全空** | V1.1 中 `DS.TREE.FOREST.CONVERSION`（树、森林与二叉树的转换）就是**零别名**的合法 concept；且 `difficulty`/`estimated_minutes` 本就允许 NULL（既有 CHECK 是 `IS NULL OR ...`）→ 全空 ≠ 容器 |
| **C-3** | **`parent_path` 只描述位置，不描述类型** | 「图」既可以是容器（`图->DFS`），也可以在某教材里是概念（图论导论）→ 位置推不出类型 |
| **C-4** | **preview 阶段无行可依** | `plan_import()` 需要在**写库前**展示「本批将创建 N 个 container / M 个 concept」；推断法在 preview 时还没有 DB 行，无从「查字段」 |
| **C-5** | **推断条件散落在每个查询里** | 每个消费点都要重复写 3~4 个 `IS NULL` 条件，且**新增一个可空字段就会静默破坏全部推断**（例如未来给容器补 `description`，推断就崩了） |
| **C-6** | **无法解决命名空间问题** | 容器占名问题与类型字段无关，推断法对此零帮助 |

**结论**：C 是「省一次 migration，换来永久语义不可靠 + 每个查询点重复脆弱逻辑」，**明确否决**。

### 2.1.4 `default` 定为 `'concept'` 而非 `'container'`（fail-loud 原则）

| 若默认 `container` | 若默认 `concept` |
|---|---|
| 某处漏写类型 → 真知识点被静默降级为目录 → **永不推荐、永不出题、永不统计**。这是**静默功能缺失**，可能数周无人发现 | 某处漏写类型 → 目录被当成知识点 → **出现在推荐里、可被关联**。这是**可见错误**，一测就发现 |

**选择 `concept`**：让「漏写」暴露为可见错误，而不是静默丢功能。

> ⚠️ 注意：`server_default="concept"` 会保留在列上，因此**未来任何忘记带 `node_type` 的 INSERT 也会拿到 `concept`**——这正是我们想要的 fail-loud 行为。

---

## 2.2 数据库迁移方案（Alembic）

### 2.2.1 设计要点

| 决策 | 取值 | 理由 |
|---|---|---|
| `nullable` | **NOT NULL** | 语义上不存在「第三态」；允许 NULL 会让每个查询都要处理 `node_type IS NULL` |
| `server_default` | **`'concept'`** | ① 让 `ADD COLUMN` 对存量行免回填；② MySQL 8 对「加带默认值的列」多为 instant DDL；③ 未来漏写时 fail-loud |
| `CHECK` | `node_type IN ('container','concept')` | 照抄既有 `ck_knowledge_points_difficulty` 范式，把词表钉死在 DB 层 |
| `INDEX` | `ix_knowledge_points_node_type` | 所有热点查询都会 `WHERE node_type='concept'`（推荐/词表/统计），需索引 |
| 数据回填 | **不需要** | 生产 `knowledge_points` 实测 **0 行**；即便非 0，`server_default` 也会填 `concept`，即「历史存量一律视为可学习知识点」——与现状语义一致（现状就是全都当知识点） |
| 版本号 | `20261002_005`，`down_revision = "20261001_004"` | 接在最新 revision 后 |

### 2.2.2 迁移骨架（本轮**不创建**，仅设计）

```python
"""add knowledge_points.node_type

Revision ID: 20261002_005
Revises: 20261001_004
"""
revision = "20261002_005"
down_revision = "20261001_004"

KP_TABLE = "knowledge_points"

def upgrade() -> None:
    # NOT NULL + server_default：存量免回填；两库语义一致
    op.add_column(
        KP_TABLE,
        sa.Column("node_type", sa.String(length=16), nullable=False, server_default="concept"),
    )
    op.create_index("ix_knowledge_points_node_type", KP_TABLE, ["node_type"])
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT → 必须走 batch 重建（与 004 同范式）
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.create_check_constraint(
            "ck_knowledge_points_node_type",
            "node_type IN ('container', 'concept')",
        )

def downgrade() -> None:
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.drop_constraint("ck_knowledge_points_node_type", type_="check")
    op.drop_index("ix_knowledge_points_node_type", table_name=KP_TABLE)
    op.drop_column(KP_TABLE, "node_type")
```

### 2.2.3 三种数据量场景的论证

| 场景 | 影响 | 说明 |
|---|---|---|
| **当前生产：0 行** | `ADD COLUMN` 是纯粹空操作 | 与 `20261001_004` 加 5 列时的情形完全一致（该 revision 已在生产验证通过） |
| **中等（数千行）** | 秒级 | MySQL 8 加「带 server_default 的 NOT NULL 列」通常为 INSTANT；SQLite 走 batch 重建（本项目测试库） |
| **未来大量（百万行）** | 需注意 | ① `NOT NULL + DEFAULT` 的加列在 MySQL 8 仍是 INSTANT（元数据级）；② 但 `CREATE INDEX` 在百万行上会耗时且占锁 → 建议**拆成两条 revision**（先加列，择低峰期再加索引），或使用 `ALGORITHM=INPLACE, LOCK=NONE`。③ 若届时需把存量行改为 container，则**必须分批 `UPDATE ... LIMIT`**，绝不一次性全表更新 |

### 2.2.4 与既有 schema 治理链路的一致性

`20261001_004` 已建立「先加列 → 再建索引 → 再 batch 建约束」的顺序范式（且注释里记录了 MySQL 1553 索引/外键顺序坑）。本 revision 沿用同一顺序，保证：`upgrade → downgrade → upgrade` 三连幂等 + `alembic check` 无 drift。

---

## 2.3 业务规则

### 2.3.1 `container`（目录节点）

**允许**
- ✅ 作为 `parent_id` 的父节点（组织结构）
- ✅ 展示在知识树 / 管理页 / 导入预览
- ✅ 被 `import_batch_id` 追溯与批次回滚
- ✅ 作为导航与筛选的「模块分组」维度

**禁止**
- ❌ 出现在 `RecommendationService` 的**任何**候选（`review_wrong` / `review_weak` / `learn_new` / `practice`）
- ❌ 产生 `user_knowledge_point_mastery` 行
- ❌ 被 `question_knowledge_points` 关联（primary / secondary 都不行）
- ❌ 进入 AI 自动标注的候选召回词表（M4）
- ❌ 作为 `knowledge_point_prerequisites` 的**任一**端点（后置或前置）
- ❌ 出现在学习计划 item / 今日建议
- ❌ 计入 `data_scale().knowledge_point_count`（V2 门禁覆盖率）

### 2.3.2 `concept`（可学习知识点）

**允许**
- ✅ mastery（掌握度计算与统计）
- ✅ 推荐（4 个动作）
- ✅ 出题与题目关联（primary / secondary）
- ✅ AI 自动标注候选
- ✅ 前置关系边端点
- ✅ 学习计划与今日建议
- ✅ 也可作为 `parent_id`（用于 concept→concept 的细分，如「二叉树遍历」下挂「先序遍历」——**本版不禁止，留作扩展**）

### 2.3.3 规则落点（「在哪一层拦」）

| 规则 | 落点 | 层 | 理由 |
|---|---|---|---|
| 容器不进推荐 | A6 `_knowledge_points()` | Service | 单点过滤，所有 4 个动作共用同一装载函数 |
| 容器不产生 mastery | **A9 `_get_knowledge_point()`** | Service | **唯一可靠关口**：mastery 的唯一写入源是「题目关联」，关住关联即关住 mastery。比在 mastery 模块加判断更内聚 |
| 容器不关联题目 | A9 | Service | 同上 |
| 容器不作前置端点 | B3 `PrerequisiteService.add()` | Service | DB 的 FK 指向同一张表，无法用外键表达「只连 concept」，只能服务层拦 |
| 容器不进 AI 词表 | D1（M4 设计） | Service | 尚未实现，写进契约 |
| 容器不计入知识库规模快照 | A7 `data_scale()` | Service | 单点（口径修正见 §1.2 脚注） |
| 容器不进 selector | A11 API `node_type` + A12 前端 | API+UI | 双保险（前端传参 + 后端过滤） |

**设计原则**：**每条规则都有一个且只有一个权威落点**，其余为可选防御。避免「六个地方各判一次，改的时候漏掉两个」。

---

## 2.4 导入系统（M2）调整

### 2.4.1 目标：`数据结构 > 图 > DFS` 的正确落型

```
导入前（CSV 一行）：  数据结构, 图>图的应用>最短路径, Dijkstra算法, ..., DS.GRAPH.SHORTEST_PATH.DIJKSTRA

导入后（DB）：
  数据结构            node_type = container   ← 路径第 1 段
  └─ 图               node_type = container   ← 路径第 2 段
     └─ 图的应用      node_type = container   ← 路径第 3 段
        └─ 最短路径   node_type = container   ← 路径第 4 段
           └─ Dijkstra算法  node_type = concept  ← 本行的「知识点名」列
```

**规则**：
- **I1（默认）**：本行「知识点名」列 → `concept`；`层级路径` 的**每个非末段** → `container`。
- **改法**：`_creation_specs()` 中给 auto-parent 的 `_CreationSpec` 补 `extras={"node_type": "container"}`；`plan.rows` 的 create 补 `extras={..., "node_type": "concept"}`。`ensure()` 无需改动（它已把 `spec.extras` 透传给 `service.create()`）。

### 2.4.2 关键边界：路径段与知识点名冲突时的裁决

真实场景：`栈` 既可能是路径段（容器），也可能某行把它定义为知识点。

| 规则 | 内容 |
|---|---|
| **I2（显式行优先）** | 若某个路径段**同时出现在任意一行的「知识点名」列**，则该段按**该行显式定义**建（该行写 concept 就是 concept） |
| **I3（矛盾检测）** | 若同一段被要求为不同类型（一行要它当 concept、另一行要它当路径段 container）→ **整批报 error**，拒绝导入，并提示「节点 X 同时被声明为 container 与 concept」 |
| **I4（已存在节点不可改型）** | 若该名字在库中已存在，则**沿用库中既有类型**（不因本次导入而改型）；若本次导入显式声明的类型与库中不一致 → 记 **warning**（不阻断，但要求管理员确认） |

> 对本项目：V1.1 中 `栈/队列/串/图/查找/排序/线性表/二叉树` 只作为容器出现（无同名 learnable 行），因此 **I2/I3 在 V1.1 上不触发冲突**，可正常导入。

### 2.4.3 如何保证「管理员导入不会产生错误类型」

| 层 | 措施 |
|---|---|
| **① 结构层（推导）** | 规则 I1 让 99% 的情况自动正确：路径段必为 container，行名必为 concept。**不需要管理员手工标类型** |
| **② 预览层（明示）** | `plan_import()` 的 preview 增加「类型」列，把「本批将创建 N 个 container、M 个 concept」显式展示给管理员（B9）。**写库前可核对** |
| **③ 门禁层（矛盾拦截）** | 规则 I3 在 `validate_rows()` / `plan_import()` 阶段把「同段两型」判为 error，**整批拒绝**（沿用 M2 既有的「任一行 error 则整批拒绝」范式） |
| **④ 可选项（显式列）** | **可选增强**：在 M2 模板新增**可选**第 8 列 `节点类型`（`container|concept`）。缺省时按 I1 推导；提供时以显式值为准。**向后兼容**：旧 7 列文件无需修改仍可导入 |
| **⑤ 入库层（DB）** | `ck_knowledge_points_node_type` 兜底，任何非法值被 DB 拒绝 |

> ⚠️ **关于第 ④ 项**：它需要改 M2 表头解析与模板下载。**本轮建议先只做 ①②③⑤**（零模板变更、零向后兼容风险），把 ④ 留作后续增强。

---

## 2.5 前端设计

### 2.5.1 管理员知识点页面（`AdminKnowledgePointsView.vue`）

| 区域 | 设计 |
|---|---|
| **表格** | 新增「类型」列，渲染徽标：📁 `container` / 🧠 `concept`（复用既有 `badge-green` / `badge-amber` 样式类） |
| **筛选** | 顶部新增「类型」下拉：全部 / 仅目录 / 仅知识点（默认全部） |
| **编辑表单** | 新增「节点类型」选择器（默认 `concept`）；**切换到 `container` 时**，给出提示「目录节点不会出现在推荐、掌握度与出题中」 |
| **父节点选择** | 允许选 container 或 concept（父子类型不设限） |
| **知识树** | **显示全部**（用户明确要求）：container 用 📁 + 加粗，concept 用 🧠 |
| **删除** | 保持既有预检逻辑（有子节点/题目/前置/mastery 时拒绝） |

### 2.5.2 知识点选择器（`KnowledgePointSelector.vue`）

- **默认：只展示 concept**（调用 `knowledgePointsApi.list({ subject, node_type: 'concept' })`）。
- 可选高级开关「显示目录节点」**默认关闭**；打开后 container 以 📁 前缀 + 置灰不可选（仅用于定位层级）。
- 把过滤放在**服务端**（A11），前端不自行过滤（避免分页/权限不一致）。

### 2.5.3 前置编辑器（`PrerequisiteEditor.vue`）

- 目标知识点与候选知识点**都只允许 concept**。
- 候选列表调用 `list({ subject, node_type: 'concept' })`。
- 若后端返回 400（B3/B4 拦截容器），toast 明确提示「目录节点不能作为前置」。

### 2.5.4 题目↔知识点关联（`QuestionKnowledgePointsModal.vue`）

- 候选**只 concept**（与 selector 同策略）。
- 后端 A9 兜底：即使前端被绕过，也无法给容器建关联。

### 2.5.5 导入预览（`KnowledgeImportPreviewTable.vue`）

- 预览表格新增「类型」列，显示「将创建为 📁/🧠」。
- 结果面板新增统计：「自动创建目录节点 N 个 / 新建知识点 M 个」。

---

## 2.6 测试方案

### 2.6.1 后端

| # | 测试 | 断言 |
|---|---|---|
| T1 | `container 不进入推荐` | 造 1 个 container + 1 个 concept（均 active）→ `RecommendationService.today(user)` 结果**不含** container id；`_knowledge_points()` 长度 == 1 |
| T2 | `container 不产生 mastery` | 对 container 调 `attach()` → 抛 `NotLearnableNode`；`user_knowledge_point_mastery` 无该 id 行 |
| T3 | `container 不允许题目关联` | primary 与 secondary 两种 role 均被拒 |
| T4 | `container 不进 AI 标注词表` | 构造词表后断言不含 container 的 name/aliases/code |
| T5 | `concept 正常工作`（回归） | 既有 `test_recommendation_service` / `test_mastery_service` / `test_prerequisite_dag` / `test_question_knowledge_points` 全绿，**且新造数据显式带 `node_type='concept'`** |
| T6 | `data_scale` 只统计 concept | 造 2 container + 3 concept → `knowledge_point_count == 3`（门禁公式不变） |
| T7 | `prerequisite_suggest` 候选无 container | mock LLM 网关，断言传入 prompt 的候选列表不含 container |
| T8 | `前置端点必须 concept` | `PrerequisiteService.add(container, concept)` → raise |
| T9 | CHECK 约束 | 直接 INSERT `node_type='group'` → DB 拒绝 |
| T10 | 默认值 | 不带 `node_type` 的 INSERT → 落库为 `concept`（fail-loud 验证） |

### 2.6.2 导入

| # | 测试 | 断言 |
|---|---|---|
| T11 | `自动创建父节点类型正确` | 导入 `数据结构, 图>DFS, DFS` → `数据结构`/`图` = container，`DFS` = concept |
| T12 | `concept 正常创建` | 单层路径（无父）的行 → concept，`parent_id=NULL` |
| T13 | `同段两型报错`（I3） | 造冲突数据 → `plan.error_rows > 0` 且 `apply_import` 整批拒绝，DB 无新行 |
| T14 | `已存在节点沿用库中类型`（I4） | 先建 container「图」，再导入把「图」当行名 → 仍为 container + warning |
| T15 | `向后兼容 7 列模板` | 现有 V1.1 CSV（7 列）导入结果与规则 I1 一致 |
| T16 | `批次回滚` | 回滚后 container 与 concept 一并删除（`_delete_leaf_to_root` 从叶子往根删） |

### 2.6.3 前端

| # | 测试 | 断言 |
|---|---|---|
| T17 | selector 过滤 | mock `list` 返回含 container → 组件只渲染 concept 项 |
| T18 | admin 类型徽标 | 表格渲染 📁/🧠；表单可切换类型并提交 |
| T19 | prerequisite editor 候选 | 候选列表不含 container |
| T20 | 导入预览类型列 | 预览表含「类型」列且取值正确 |

### 2.6.4 schema 治理

| # | 测试 | 断言 |
|---|---|---|
| T21 | `upgrade → downgrade → upgrade` 幂等 | 三连无错 |
| T22 | `alembic check` 无 drift | 与 `Base.metadata` 一致 |
| T23 | 词表三方一致 | `node_type` 词表在 model / schema / service 常量三处同源（照抄 `KP_DIFFICULTY_LEVELS` 的钉死测试范式） |

---

# 第三阶段：开源方案参考

> 原则：**只提炼值得借鉴的设计思想，不引入任何新框架/新依赖/新基础设施。**

## 3.1 1EdTech CASE 1.1

| 借鉴点 | 说明 | 对本方案的映射 |
|---|---|---|
| **`CFItemType`（显式类型字段）** | CASE 不在「框架」上打布尔开关，而用**类型字段**区分 item 的角色 | ✅ 直接对应 `node_type`；印证「枚举 > 布尔」 |
| **不同层级用不同 item type** | 官方明确建议：不同粒度的条目应使用不同的 type 值，而不是复用同一个 | ✅ 印证 `container` vs `concept` 分型；且为未来加第三个值留了路径 |
| **Framework vs Item 分离** | 「框架/容器」与「可评估条目」是两类对象 | ✅ 这正是 container vs concept 的本质 |
| **稳定 identifier（GUID）发布后不变** | 改名/移动层级不改 ID | ✅ 本项目 `code` 已遵守（G7 稳定编码），`node_type` 进一步声明「身份」 |
| **`CFAssociation` 词表区分 isChildOf / isPartOf / precedes / isRelatedTo** | 层级关系、包含关系、先后关系、相关关系是**不同语义**的边 | ✅ 本项目 `parent_id`(part-of) 与 `knowledge_point_prerequisites`(precedes) 已分离；本方案进一步限制前置边只连 concept |
| **`replacedBy` 处理退役标识** | 发布过的标识不建议删除，而应保留并指向替代者 | ✅ 本方案 §2.2 说明：**因 V1/V1.1 未发布，无需保留旧 code**；但一旦发布，未来改型必须用 replacedBy 范式 |

**不采纳的部分**：CASE 的完整 JSON 序列化格式、GUID 体系、`CFDocument/CFPackage` 打包与传输机制 —— 本项目不需要对外交换标准文档，引入成本大于收益。

## 3.2 Learning Commons Knowledge Graph

| 借鉴点 | 说明 | 对本方案的映射 |
|---|---|---|
| **`StandardsFrameworkItem`（标准条目）与 `LearningComponent`（可教学组件）是两类节点** | 一条课标要求 ≠ 一个可教学粒度能力；后者是从前者拆解出来的 | ✅ 与本方案 container/concept 高度同构 |
| **`IS_PREREQUISITE_OF` 只连可教学组件** | 前置关系建立在**能力**之间，不建立在课标条目之间 | ✅ 印证「前置边端点必须是 concept」（B3） |
| **属性图模型（`nodes.jsonl` + `relationships.jsonl`）** | 节点与边分离建模 | ⚠️ 本项目已用「单表 + 边表」实现同等效果，**不需要改图数据库** |
| **「earlier in a learning progression」≠「strict prerequisite」** | 官方明确区分「学习进阶中更早」与「严格前置」 | ✅ 已在《V1.1设计说明》§11 落地为「硬前置 / 软前置 / related」三分 |
| **Eedi Misconceptions Graph（误区数据集）** | 误区作为独立资产挂在知识点下 | ⚠️ 与本方案无关（误区目前记录在审计表，未建表）；记录备用 |

**不采纳的部分**：GraphQL/属性图查询层、其发布/版本化流水线、跨框架对齐（exactMatchOf）机制。

## 3.3 K12-KGraph

| 借鉴点 | 说明 | 对本方案的映射 |
|---|---|---|
| **7 类节点 / 9 类边** | 类型先行，边类型化 | ✅ 印证「类型字段是图谱化的前提」；但本项目**只取 2 类节点**，不盲目照搬 |
| **全局约束：所有文本属性必须能被源教材内容显式支撑** | 不允许凭空生成节点/属性 | ✅ 直接印证本方案 §2.1.3 否决「NULL 推断」——类型也必须来自**导入源的显式结构（路径）**，不能猜 |
| **节点粒度对齐教材目录** | 节点应与可教学内容对齐，而非与章节标题对齐 | ✅ 印证「路径段=container，行名=concept」的推导规则 |

**不采纳的部分**：其 LLM 抽取流水线、大规模自动构建流程（本项目已有 M2 导入 + M4 标注规划）。

## 3.4 其他

| 来源 | 借鉴点 |
|---|---|
| MoocRadar（已在 `prerequisite_suggest.py` docstring 引用） | 「LLM 只提议、专家确认」——本方案延续：类型由**结构推导**，不由模型猜测 |
| 通用 KG 工程实践 | 「容器节点不参与度量」是一条普适原则（类似目录不计入文档数） |

**总结**：三个开源方案分别在**类型显式化**（CASE）、**结构层 vs 可教学层分离**（Learning Commons）、**属性必须有源可依**（K12-KGraph）上印证了同一结论：**用显式枚举类型字段区分 container/concept，并让所有下游消费者按类型过滤**。

---

# 第四阶段：风险评估

## 4.1 如果**现在不修改**

| 阶段 | 会出现的问题 | 严重度 |
|---|---|---|
| **M4 AI 自动标注** | 召回词表 = 同 subject 全部 `name + aliases + code` → 「树」「排序」「图」「查找」等**目录名命中题干** → 容器被 LLM 标为知识点 → 该标注**无法出题**（容器没题）→ 标注质量下降 + 大量人工返工。**这是最先爆且最贵的地方** | 🔴 高 |
| **M5 推荐** | `_knowledge_points()` 只过滤 `status` → 容器进 `learn_new` 候选 → 用户被推荐「学习『排序』」→ 点进去无题可做，掌握度永远 50、学不会，推荐循环空转 | 🔴 高 |
| **M6 质量系统** | K1「覆盖率」/ K2「孤立知识点」若把容器计入分母 → **覆盖率虚高**（M6 尚未实现，需在其设计中明确分母只取 concept）。另需注意：**真实存在的 `kp_coverage` 污染路径**是「某题被关联到 container」→ 该题仍计入 `tagged_question_count` → 覆盖率虚高 → 影响 V2 BKT 门禁（`min_kp_coverage=0.8`）。此路径由 A9 兜住 | 🟠 中高 |
| **掌握度** | 只要有一次把题目误关联到容器，容器就产生 mastery 行 → `total`/`weak_count`/`average_score` 全部被污染，且**无法自动区分** | 🟠 中高 |
| **学习路径** | 前置边可连容器 → `learning_path()` 返回「数据结构 → … → 快速排序」，把目录当学习步骤 | 🟡 中 |
| **V2 门禁快照** | `data_scale().knowledge_point_count` 含容器 → **规模快照口径失真**（快照是门禁透明度与审计依据）。注意：该值当前**不直接驱动**门禁公式，故严重度低于「题目被标到容器」那条路径 | 🟡 中低 |

**结论**：不修改 = 在 M4/M5/M6 三个后续阶段同时埋雷，且**越晚修越贵**（届时已有真实标注/推荐/掌握度数据产生脏行，需要数据清理 migration）。

## 4.2 如果**修改**

### 成本

| 维度 | 内容 |
|---|---|
| **影响文件** | 后端 **14**（模型 1 / migration 1 / schema 1 / service 5 / api 2 + 测试 4~6）<br>前端 **5**（3 组件 + admin 页 + utils/api/types）<br>文档 **2**（M4 设计补 D1/D2 约束 + 本方案转正） |
| **代码改动量** | 后端核心约 **60~90 行**（含校验与过滤），前端约 **80~120 行**（含徽标/表单/筛选），测试约 **300~450 行** |
| **migration** | 1 个 revision，`upgrade`+`downgrade` 约 25 行；生产 0 行 → **线上零风险** |
| **预计工作量** | **约 1.5 ～ 2.5 人日**（不含视觉细调与后续 M4/M6 实现）—— 拆分：模型+migration+schema 0.3d / service 过滤 0.4d / 导入 0.3d / 前端 0.6d / 测试 0.7d |
| **不可逆风险** | **低**：`downgrade` 只删本 revision 新增对象；且若将来要回滚类型语义，`node_type` 不会被下游误用（默认 concept = 现状行为） |
| **回归风险** | 中。所有既有测试里造的知识点数据若不带 `node_type`，会因 `server_default='concept'` 自动通过 → **回归风险反而很小**；但需新增 T1~T10 覆盖新语义 |

### 关键风险点与规避

| 风险 | 规避 |
|---|---|
| 某处漏加 `node_type='concept'` 过滤 | 用「单一权威落点」表（§2.3.3）+ T1/T5/T6 回归测试断言 |
| 前端只过滤、后端没过滤 | A11 后端 `node_type` 参数为**权威**，前端只是传参（T17 验证） |
| 导入把已有 concept 误降为 container | 规则 I4「已存在节点沿用库中类型」+ warning |
| 未来加第三个类型时漏改 CHECK | T9 + T23（词表三方一致钉死测试） |
| MySQL 大表加索引锁表 | §2.2.3：未来拆两条 revision / `LOCK=NONE` |

## 4.3 建议的实施顺序（待确认后执行）

```
Step 1  schema：model 加列 + CHECK + 新 migration + schema 三方一致测试
Step 2  service 过滤：A6/A7/A8（推荐、统计、LLM 候选）
Step 3  关联关口：A9（question_knowledge_point_service 拒绝 container）+ B3（前置端点）
Step 4  导入：A10（auto-parent=container / 行=concept）+ I3 矛盾检测
Step 5  API：A4/A5/A11（list_all / create / list 接口参数）
Step 6  前端：A12（4 处）+ B8/B9/B10
Step 7  测试：T1~T23 全量 + CI 双库（MySQL + SQLite）
Step 8  文档：M4 设计补 D1/D2 约束；本方案转「已实施」
Step 9  （可选）数据修复：若届时库中已有脏行（容器被关联/有 mastery），用一次性脚本清理
```

---

## 附录 A：影响面全量索引（按文件）

| 文件 | 类别 | 说明 |
|---|---|---|
| `backend/app/models/knowledge.py` | A1 | `KnowledgePoint` 加 `node_type` |
| `backend/alembic/versions/20261002_005_*.py` | A2（新建） | migration |
| `backend/app/schemas/knowledge.py` | A3 | Create/Update/Read 加字段 |
| `backend/app/services/knowledge_point_service.py` | A4/A5 | `list_all` 参数、`create` 参数、`_assert_node_type` |
| `backend/app/services/recommendation.py` | A6/A7, B1/B2 | `_knowledge_points` / `data_scale` / `_legacy_index` / `_question_primary_kp_map` |
| `backend/app/services/prerequisite_suggest.py` | A8 | `_candidates` |
| `backend/app/services/question_knowledge_point_service.py` | A9 | `_get_knowledge_point` 拒绝 container |
| `backend/app/services/knowledge_import.py` | A10 | `_creation_specs` + 冲突检测 |
| `backend/app/services/prerequisite.py` | B3 | `add()` 校验端点类型 |
| `backend/app/services/mastery.py` | B5 | `list_weak` 防御过滤 |
| `backend/app/api/routes/knowledge_points.py` | A11, B4 | list 参数、前置接口校验 |
| `backend/app/api/routes/mastery.py` | B6 | summary 过滤 |
| `backend/app/api/routes/questions.py` | A9 间接 | 经 service |
| `web/src/components/KnowledgePointSelector.vue` | A12 | 默认只 concept |
| `web/src/components/PrerequisiteEditor.vue` | A12 | 候选只 concept |
| `web/src/components/QuestionKnowledgePointsModal.vue` | A12 | 候选只 concept |
| `web/src/views/admin/AdminKnowledgePointsView.vue` | A12 | 类型徽标 + 表单 |
| `web/src/views/admin/AdminKnowledgeImportView.vue` | B9 | 预览类型列 |
| `web/src/components/KnowledgeImportPreviewTable.vue` | B9 | 预览类型列 |
| `web/src/utils/knowledgePoints.ts` | B8 | 类型展示 |
| `web/src/api/knowledgePoints.ts` | B10 | 类型 + 参数 |
| `web/src/types/index.ts` | B10 | 类型定义 |
| `docs/大阶段4实施设计方案.md` | D1/D2 | 补「词表只取 concept」等约束 |

---

## 附录 B：与既有《知识节点类型技术审计报告.md》的关系

| 项 | 审计报告（上一轮） | 本文（本轮） |
|---|---|---|
| 定位 | 结论性审计：证明 P0 存在 + 方案 A/B/C 比较 | **可执行落地版**：字段定义、migration 骨架、业务规则、导入规则、前端设计、测试清单、工作量 |
| P0 结论 | 确认存在，推荐方案 A | **一致**，并给出 fail-loud 默认值论证 |
| 代码路径 | 18 处（12 直接 + 5 间接） | **扩充为 30 处**（A12 + B10 + C6 + D2），逐处给出改法与理由 |
| 是否落地 | 否 | 否（本轮仍只出方案） |

---

*本文档为只读审计与设计产物，本轮不涉及任何代码、migration、部署或提交变更。*
