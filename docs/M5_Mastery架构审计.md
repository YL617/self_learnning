# M5 个性化学习推荐系统 · 只读架构审计报告

- 审计日期：2026-10-11
- 审计方式：**只读**（逐文件阅读真实代码 + 生产只读探针），未修改任何文件
- 生产基线：Git `f65e88ee685127440dc9cc9dd3afcf65d27528f9` / Alembic `20261010_007 (head)`
- 生产数据：knowledge_points **78**（concept 56 / container 22）、import_batches 1、questions 8、qkp **0**、mastery **0**、prerequisite **0**

---

## 0. 结论速览（TL;DR）

| 维度 | 结论 |
|---|---|
| M5 目标实现度 | **后端引擎约 90% 已存在**（2026-10-01 引入，早于 M4），并非"从零实现" |
| 掌握度模型 | ✅ 表 + 服务 + 算法 + API + 13 测试 **全部已有**；正确率/错误次数为**可派生量**，无需存储 |
| 前置关系系统 | ✅ 模型 + 服务 + 5 组 API + 图算法 + LLM 提议 + 20 测试 **全部已有** |
| 推荐系统 | ✅ `RecommendationService` + `GET /recommendations/today` + 前端卡片 + 29 测试 **全部已有** |
| **是否需要 migration** | ❌ **不需要**（0 migration）——所有表/列/约束均已存在并在生产就位 |
| 真正的缺口 | ① 用户端缺**专职"我的学习计划"页面**（现仅 Dashboard 卡片，limit=3）② 用户端缺**学习路径可视化**（`/path` API 就绪但仅管理端消费）③ **前置数据为 0 → 推荐排序退化**（生产实测 5 条建议全部同分 84.5） |

> **一句话**：M5 的"引擎"已经造好了，缺的是**面向用户的入口/可视化**与**驱动个性化的数据**（前置边 + 掌握度）。因此 M5 应定位为"**引擎启用 + 前端补全**"，而**不是重写推荐算法**。这也严格符合你的红线「禁止重建已有功能」。

---

## 1. 掌握度模型（Mastery）

### 1.1 表结构 —— `user_knowledge_point_mastery`

模型：`backend/app/models/learning.py:216-249`（`UserKnowledgePointMastery`）
迁移：`backend/alembic/versions/20261001_002_add_user_knowledge_point_mastery.py`

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | PK | — |
| `user_id` | FK users(CASCADE) | 归属用户 |
| `knowledge_point_id` | FK knowledge_points(RESTRICT), index | 归属知识点 |
| `mastery_score` | int, default 50 | **熟练程度** 0~100（确定性算法维护，非 AI） |
| `attempt_count` | int, default 0 | 作答次数 |
| `correct_count` | int, default 0 | 答对次数 |
| `correct_streak` | int, default 0 | **连续答对** |
| `last_answered_at` | datetime? | **最近学习时间**（最近作答） |
| `last_correct_at` | datetime? | 最近答对时间 |
| `last_reviewed_at` | datetime? | 最近复习时间 |
| `created_at` / `updated_at` | datetime | — |

约束：`UniqueConstraint(user_id, knowledge_point_id)` —— 同一 (用户, 知识点) 唯一。

### 1.2 服务与算法 —— `backend/app/services/mastery.py`

- **确定性、可解释、零 AI**：`mastery_score` 恒 0~100 整数，全部权重集中在模块常量区（`mastery.py:29-51`）。
- 打分核心（`compute_delta`，`mastery.py:67-94`）：
  ```
  答对： + GAIN_BASE(16) × 难度权重 × 角色权重 × 复习系数(1.25) × 余量缩放 + 连胜奖励(1.5/题, 封顶 5)
  答错： - LOSS_BASE(14) × 难度权重 × 角色权重 × 当前分数缩放
  ```
  难度权重 `easy 0.8 / medium 1.0 / hard 1.3`；角色权重 `primary 1.0 / secondary 0.5`；余量缩放 `HEADROOM_FLOOR=0.35`（越接近 0/100 变化越慢，防止一题爆表）。
- 读取层**双防御**：`list_for_user` / `average_score` / `count_for_user` / `count_weak` 全部 `JOIN knowledge_points WHERE node_type='concept'`（`mastery.py:139-237`）→ **container 永不进入掌握度统计**。
- 薄弱判定：`WEAK_THRESHOLD=60` 且 `attempt_count>=1`（`list_weak`，`mastery.py:161-187`）。

### 1.3 答题后的更新流程（时序）

`backend/app/api/routes/questions.py:491-544` → `_apply_learning_state`（`questions.py:428-470`）

```
POST /questions/{id}/answers
  → _resolve_answerable_question（owner / admin / visibility='shared'，他人私题 404）
  → check_answer(question, user_answer)  → is_correct
  → AnswerRecord 落库
  → load_knowledge_point_signals(question_id)       # 读 qkp 结构化关联
  → build_evaluation(...)                            # EvaluationResult（含难度解析）
  → MasteryService.apply_evaluation(...)             # 逐 signal 更新 mastery（primary 权重大）
  → 答错 → WrongBookItem upsert + schedule_first_review / apply_review_outcome
  → award_coins / award_pet_exp / record_daily_stat
  → 单一事务 commit（任一异常整体回滚，杜撰"答案已存但掌握度未更新"半完成态）
```

- 难度解析：`resolve_difficulty`（`evaluation.py:67-72`）——显式 `difficulty` 优先，否则题型映射（choice=easy/fill=medium/short_answer=hard）。
- 无结构化知识点的 legacy 题目：`signals` 为空 → `apply_evaluation` 直接返回 `[]`，行为与旧版一致（`mastery.py:277-278`）。

### 1.4 能力矩阵（你点名要求的五项）

| 要求能力 | 是否支持 | 实现方式 | 结论 |
|---|---|---|---|
| 正确率 | ✅ 可派生 | `correct_count / attempt_count`（表未存冗余列） | 无需 migration，读取时计算 |
| 最近学习时间 | ✅ 已存储 | `last_answered_at` | 直接可用 |
| 连续答对 | ✅ 已存储 | `correct_streak` | 直接可用 |
| 错误次数 | ✅ 可派生 | `attempt_count - correct_count` | 无需 migration |
| 熟练程度 | ✅ 已存储 | `mastery_score`(0~100) + 前端 `masteryLevel` 三级映射 | 直接可用 |

### 1.5 缺失能力 / 是否需要 migration / 可否复用

| 项 | 结论 |
|---|---|
| 缺失能力 | 仅"**正确率、错误次数**"两个派生指标未持久化——**刻意不存**，避免冗余列与不一致；读取时计算即可 |
| 是否需要 migration | **不需要**。表结构与约束完整，已在生产（`20261001_002`） |
| 是否可以复用 | **完全复用**。M5 无需触碰 mastery 表与服务；只需在推荐打分/前端展示中读取现有字段 |

---

## 2. 前置关系系统（Prerequisite DAG）

### 2.1 模型 —— `knowledge_point_prerequisites`

模型：`backend/app/models/knowledge.py:222-252`（`KnowledgePointPrerequisite`）
迁移：`backend/alembic/versions/20261001_003_add_knowledge_point_prerequisites.py`

| 字段 | 语义 |
|---|---|
| `knowledge_point_id` | **后置**（依赖方） |
| `prerequisite_id` | **前置**（先学方） |
| `strength` | 0~100，`>=60` 视为**硬前置**（未满足则阻塞），`<60` 仅作学习顺序建议 |
| `status` | `active` / `disabled` |
| `source` | `manual` / `llm` / `import` |
| `note` | 备注 |

约束：`UniqueConstraint(knowledge_point_id, prerequisite_id)` + `CheckConstraint(knowledge_point_id <> prerequisite_id)`（DB 级拒绝自环）。

> **与 `parent_id` 严格分离**：`parent_id` 是归属层级（树，单父）；本表是前置依赖（多对多 DAG）。语义不混用，即使复用 `parent_id` 也无法表达"C 同时依赖 A 和 B"。

### 2.2 API 清单（均已挂载在 `/api/v1`）

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/knowledge-points/{id}/prerequisites` | 登录用户 | 前置列表 + 该用户满足度（`satisfied`/`blocking`/`ready`） |
| POST | `/knowledge-points/{id}/prerequisites` | **管理员** | 新增前置边（拒绝 container 端点 / 自环 / 成环 / 重复） |
| DELETE | `/knowledge-points/{id}/prerequisites/{prerequisite_id}` | **管理员** | 删除前置边 |
| GET | `/knowledge-points/{id}/path` | 登录用户 | **学习路径**（传递前置集合 + 拓扑序 + 逐步掌握度/satisfied/is_target） |
| POST | `/knowledge-points/{id}/prerequisites/suggest` | **管理员** | LLM **只提议不落库**（`/prerequisite_suggest.py`，MoocRadar 范式） |

路由实现：`backend/app/api/routes/knowledge_points.py:221-359`。

### 2.3 服务与图算法 —— `backend/app/services/prerequisite.py`

| 能力 | 方法 | 说明 |
|---|---|---|
| 传递前置集合 | `prerequisite_closure` | BFS + visited（成环不死循环）；遍历上限 `MAX_TRAVERSAL_NODES=5000` |
| **解锁计数** | `unlock_count` | 学会本点后可解锁的传递后置数（推荐打分因子） |
| 拓扑序 | `topological_order` | 前置在前、同层按 id 升序；含环也保证返回 |
| 学习路径 | `learning_path` | closure + 拓扑序（含目标本身） |
| 满足度 | `statuses_for` / `is_ready` | mastery 缺失视为**未满足**；`READY_THRESHOLD=70` |
| 可学习闸门 | `_assert_exists` | **两端都必须是 concept**，container 一律拒绝（服务层权威落点） |
| 写保护 | `add` | 自环 → 重复 → 成环 三重拦截 |

### 2.4 concept A → prerequisite → concept B 支持情况

✅ **完整支持**。`(knowledge_point_id=B, prerequisite_id=A)` 表"先学 A 才能学 B"。语义细节：

- `strength >= 60` → **硬前置**：A 未达 70 分时，B 在推荐中被**排除出 `learn_new`**（`recommendation.py:711-715`）。
- `strength < 60` → **软前置**：不阻塞，仅影响排序与理由文案。
- 两端**都必须是 concept**——container 不可能出现在前置边任一端。

### 2.5 如何用于学习路径推荐

| 用途 | 已有落点 |
|---|---|
| 阻塞未就绪知识点 | `learn_new` 候选过滤（`recommendation.py:711-715`） |
| 给"解锁下游多"的点加权 | `unlock_count` → `unlock_factor`（`recommendation.py:476`） |
| 生成有序学习路线 | `GET /knowledge-points/{id}/path` → `LearningPathOut` |
| 抽题 | `/knowledge-points/{id}/questions` 反查（含 shared 题，用户端可答） |

### 2.6 缺失 / migration / 复用

| 项 | 结论 |
|---|---|
| 缺失 | 前置数据 **0 条**（生产实测）；无"用户端学习路径可视化"（API 有、UI 无） |
| 是否需要 migration | **不需要**（表/约束/API 全在） |
| 是否可以复用 | **完全复用**；M5 只需补前端路径视图 + 引导管理员建立前置边 |

---

## 3. 推荐系统（Recommendation V1）

### 3.1 Pipeline —— 你的设计输入/输出 ↔ 现有实现映射

**输入 User Profile**（你要求 `{user_id, mastery, history, wrong_questions, learned_points}`）

| 你的输入 | 现有实现来源 | 文件 |
|---|---|---|
| `mastery` | `MasteryService.list_for_user(user_id)` | `recommendation.py:389-392` |
| `history` | `AnswerRecord` 最近 5 次（`_recent_answer_stats`，仅 primary 关联） | `recommendation.py:426-446` |
| `wrong_questions` | `WrongBookItem`（`mastered=false` 且 `next_review_date<=today`） | `recommendation.py:537-545` |
| `learned_points` | `mastery_score` 的 key 集合（有记录即"学过"） | `recommendation.py:709` |
| 目标/计划 | `UserProfile.goals/weak_subjects/major` + `StudyPlan` 文本分词 | `recommendation.py:406-424` |

**输入 Knowledge Graph**（你要求 `{concepts, containers, prerequisites}`）

| 你的输入 | 现有实现 | 文件 |
|---|---|---|
| `concepts` | `_knowledge_points()`：`status='active' AND node_type='concept'`（**唯一候选装载口**，container 天然出局） | `recommendation.py:375-387` |
| `containers` | 不进入任何动作（同一过滤保证） | 同上 |
| `prerequisites` | `PrerequisiteService.edge_pairs()` | `recommendation.py:316` |

**输出 Recommendation**（你要求 `{recommended_nodes, reason, priority, estimated_time}`）

| 你的要求 | 现有字段（`RecommendationItem`，`recommendation.py:116-127`） |
|---|---|
| `recommended_nodes` | `knowledge_point_id` + `knowledge_point_name` + `subject` |
| `reason` | `reason`（模板化、数据驱动、可核对） |
| `priority` | `order`（1..N）+ `score`（浮点）+ `components`（分解） |
| `estimated_time` | `estimated_minutes` |
| （额外） | `action` + `action_label`（4 类动作）、`question_ids`（可直接开练的题） |

### 3.2 打分公式与权重（唯一来源：`recommendation.py:70-99`）

```
score = BASE[action]
      × urgency      （错题逾期：+0.15/天，封顶 1.6）
      × gap          （掌握度缺口：1 + 0.6 × (100-score)/100）
      × goal         （命中目标：×1.25）
      × unlock       （解锁加成：1 + 0.12×解锁数，封顶 +0.6）
      × recency      （最近 3 天练过：×0.6）
```

| 动作 | 基础分 | 预估时长 | 触发条件 |
|---|---|---|---|
| `review_wrong` 复习错题 | 100 | 15 min | 错题已到复习日 |
| `review_weak` 巩固薄弱 | 72 | 20 min | `mastery<60` 且作答≥1 |
| `learn_new` 学习新知 | 52 | 30 min | 无 mastery 记录 且 无硬前置阻塞 |
| `practice` 加练 | 34 | 15 min | `mastery>=60` 且作答<2 |

去重：**同一知识点只保留最高分动作**（`recommendation.py:350-355`）；输出按 `(-score, kp_id)` 稳定排序。

### 3.3 V2 门禁（防过早引入复杂模型的护栏，`recommendation.py:101-245`）

- BKT 参数拟合：总作答 ≥5000 且 单点作答中位数 ≥30 且 用户 ≥50 且 知识点覆盖率 ≥80%
- 深度 KT：总作答 ≥100000 且 用户 ≥1000
- 未达标 → `check_bkt_gate` / `check_deep_kt_gate` 返回 `allowed=False`。**这与你"M5 禁止深度学习/LLM 实时推荐"的要求一致且已有硬门禁。**

### 3.4 生产实测行为（只读探针，证据）

```
GET /api/v1/recommendations/today?limit=5   （admin uid=1）
  date: 2026-10-11 | weak_threshold: 60 | ready_threshold: 70 | items: 5
  - 1 learn_new | 数据结构基本概念 | score 84.5 | 没有前置知识点，可以直接开始；命中你的学习目标…
  - 2 learn_new | 抽象数据类型（ADT） | score 84.5 | 同上
  - 3 learn_new | 算法的定义与特性 | score 84.5 | 同上
  - 4 learn_new | 时间复杂度分析 | score 84.5 | 同上
  - 5 learn_new | 空间复杂度分析 | score 84.5 | 同上

GET /api/v1/mastery/summary
  {"total":0,"weak_count":0,"average_score":0.0,"today_review_count":2,"weak_threshold":60}
```

**判读**：接口**端到端可用**；但因 `prerequisite=0` + `mastery=0`，全部候选 `gap/unlock/urgency` 因子相同 → **5 条建议同分 84.5，排序退化**（仅靠 id 兜底）。即"个性化"目前**引擎在、数据缺**。

### 3.5 缺失 / migration / 复用

| 项 | 结论 |
|---|---|
| 缺失 | ① 生产**前置边 0 条**、掌握度 0 条 → 排序退化；② 无"用户端专职推荐/计划页面"；③ 无"推荐结果反馈/忽略"闭环（V1 刻意不做，符合"第一版不引入复杂算法"） |
| 是否需要 migration | **不需要**。推荐是**纯只读**，不写任何业务表（`recommendation.py:8` 明确"建议不自动落入 PlanItem"） |
| 是否可以复用 | **完全复用**；M5 只需补前端 + 数据引导 |

---

## 4. 前端现状（已消费 vs 未消费）

| 能力 | API | 前端状态 | 位置 |
|---|---|---|---|
| 今日建议卡片 | `/recommendations/today` | ✅ 已消费（**仅 Dashboard**，`limit=3`；"开始"只做页面跳转，不落计划） | `web/src/components/RecommendationCard.vue` + `views/DashboardView.vue:192` |
| 掌握度总览 + 薄弱列表 | `/mastery/summary` `/mastery/weak` | ✅ Dashboard 已消费 | `views/DashboardView.vue:34-60,199-217` |
| 知识点掌握度 | `/mastery/{kp_id}` | ✅ M4 知识图谱页已消费（作答次数/正确/连胜） | `views/KnowledgeExploreView.vue:75-84,185-191` |
| **学习路径** | `/knowledge-points/{id}/path` | ⚠️ **仅管理端** `PrerequisiteEditor` 消费，**用户端无** | `components/PrerequisiteEditor.vue` |
| 前置列表/满足度 | `/knowledge-points/{id}/prerequisites` | ⚠️ 同上（管理端） | 同上 |
| 推荐落计划 | 无（设计如此） | — | — |

**结论**：用户端有"**卡片**"无"**页面**"；有"**掌握度**"无"**学习路径**"。

---

## 5. 真实缺口清单（按必要性排序）

| # | 缺口 | 类型 | 影响 | 建议归属 |
|---|---|---|---|---|
| G1 | 用户端缺**专职「我的学习计划」页面**（今日推荐 ↓ 薄弱知识点 ↓ 推荐原因 ↓ 开始学习，一屏贯通） | 前端 | M5 明确要求的可见形态缺失 | **M5 必做** |
| G2 | 用户端缺**学习路径可视化**（`/path` 已就绪，仅管理端用） | 前端 | "学习路径"这一 M5 目标对用户不可见 | **M5 必做** |
| G3 | **前置边 0 条** → 推荐排序退化（实测 5 条同分 84.5） | 数据 | "个性化"名不副实 | **M5 必做（引导/种子）** |
| G4 | 掌握度 0 条 → 薄弱推荐为空 | 数据 | 需真实作答产生；非代码问题 | 运营/数据 |
| G5 | 前端"开始"仅跳转，未把推荐锚定到具体题目/知识点 | 前端体验 | `question_ids` 已下发但未用 | M5 增强（可选） |
| G6 | 推荐无"今日已完成/忽略"反馈 | 产品 | V1 刻意不做 | M6+（可选） |
| G7 | `KnowledgePoint.estimated_minutes` 未被推荐使用（推荐用动作常量时长） | 后端微调 | 个性化时长可更准 | M5 可选（优先级低） |
| G8 | API 命名 `GET /recommendations/today` vs 你提的 `GET /user/recommendations` | 命名 | 语义等价，仅命名差异 | 可保留现状 + 说明 |

### 数据库变更需求结论

> **M5 第一版需要 0 个 migration。**
> 理由：所有数据模型（mastery 表、prerequisite 表、qkp 表、questions/difficulty/visibility）均已存在并在生产就位；推荐 V1 为纯只读派生，不新增持久化。
> 仅当决定做 G6（推荐反馈/忽略）或 G7（按知识点时长）时才需要新增列/表——**建议推迟到 M6**，避免为已完备的引擎引入不必要 schema 变更。

---

## 6. 风险与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| 误判为"要重写推荐" | 引擎已存在，重写违反"禁止重建已有功能"且引入回归风险 | 本报告以文件+行号证实现状；M5 定位为"启用+补全" |
| 前置数据来源 | 56 concept 目前无前置边；若全量 LLM 生成需人工确认（`suggest` 只提议） | 走 `POST /prerequisites/suggest` + 管理员逐条确认；或先建**高质量种子**（如按 V1.2 层级/难度派生候选） |
| container 红线 | 前置边两端必须 concept（服务层拦截）；推荐候选唯一装载口已过滤 container | 复用现有闸门，不新增绕过路径 |
| 排序退化 | 无数据时 `learn_new` 同分 | 前端按 `order` 展示即可；补数据后自然分化 |
| 主机资源 | 生产 1.6GiB 内存偏紧（10-10 OOM 已实锤） | 与 M5 无关，但部署前建议加 swap |

---

## 7. 待你确认的决策点（进入第二阶段前）

1. **M5 范围**：确认定位为"**引擎启用 + 前端补全**"（不重写算法、0 migration）？
2. **G1 页面**：新增独立路由 `/my-plan`（"我的学习计划"），还是增强 `DashboardView`？
3. **G2 路径**：学习路径放在知识图谱页内（点知识点 → 看路径），还是独立视图？
4. **G3 前置数据**：本阶段只做**引导入口**（管理员用 suggest 建边），还是要我给出"基于 V1.2 数据的种子前置候选清单"（需你确认后另行执行）？
5. **G8 命名**：保留 `GET /recommendations/today`，还是额外暴露 `GET /user/recommendations` 别名？
6. **G6/G7**：是否**明确推迟**到 M6（推荐"是"，以保持 0 migration 与最小侵入）？

---

**审计结论：M5 个性化推荐系统的后端引擎已在位、生产可用；真正缺口是「用户端入口/可视化」与「个性化数据」。本阶段为增量补全，非重写；需要 0 个 migration。等待确认后再进入第二阶段（设计方案）。**
