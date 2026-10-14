# M5 Step 4 前置关系现状审计

> 阶段：M5 Step 4「前置关系数据建设与推荐激活」· Step 0 只读分析
> 约束遵守：**未修改任何代码 / 未建 migration / 未调用任何写接口 / 未写入生产**；生产侧仅执行只读 SQL 计数与只读清单导出。
> 目的：确认前置关系系统的真实能力边界，判断「导入 50 条候选」需要多少改动，并预判激活后的用户可见变化。

---

## 一、结论速览

| 问题 | 结论 |
|---|---|
| 前置边表结构是否够用 | ✅ 够用，**50 条候选全部可表达** |
| strength 语义 | 0~100；**≥60 为「硬前置」（阻塞），<60 仅为顺序建议**（`BLOCKING_STRENGTH=60`） |
| 创建入口 | ✅ 已有：`POST /knowledge-points/{id}/prerequisites`（仅管理员），**单条**写入 |
| 是否支持批量导入 | ❌ **不支持**（无 batch 端点、无导入批次表、无 CSV 入口） |
| 是否有审核机制 | ⚠️ **半有**：无独立审核表/状态机；「人审」= 管理员在前端点「采纳／添加」才落库（LLM 只提议） |
| 是否需要后端修改 | ❌ **不需要**（50 条可经既有单条 API 完成；仅「真正 batch + 批次回滚」才需后端改动） |
| 是否需要 migration | ❌ **不需要**（0 张新表、0 个新列） |
| 本阶段是否写库 | ❌ 未写入；生产 `knowledge_point_prerequisites` 仍为 **0 行** |

---

## 二、生产实测基线（只读）

只读 SQL（`docker exec ai-study-mysql mysql -uroot -p*** -N -e "USE ai_study; ..."`）：

| 指标 | 实测值 |
|---|---|
| `knowledge_points` 总数 | **78** |
| ├ `concept`（可学习） | **56** |
| └ `container`（目录） | **22** |
| `knowledge_point_prerequisites`（前置边） | **0** |
| └ `status='active'` | 0 |
| `user_knowledge_point_mastery`（掌握度） | **0** |
| `users` | 1 |
| `questions` | 8 |

**→ 与 M5 架构审计结论一致：前置边 = 0、掌握度 = 0，推荐打分因此退化为同分。**

节点清单（78 行，id / code / node_type / parent_id / 难度 / 学时）已完整导出并本地解码核对：
- 56 个 concept **全部挂在 container 之下**（无孤立 concept、无 concept 直挂根）；
- 22 个 container 中 8 个为一级章、14 个为二级／三级目录。

---

## 三、数据模型现状

`app/models/knowledge.py` → `KnowledgePointPrerequisite`（表 `knowledge_point_prerequisites`）：

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | int | PK | |
| `knowledge_point_id` | int | FK→`knowledge_points.id` **RESTRICT** | **后置**（依赖方） |
| `prerequisite_id` | int | FK→`knowledge_points.id` **RESTRICT**，**有索引** | **前置**（必须先学） |
| `strength` | int | default 100 | 0~100，见第四节 |
| `source` | varchar(16) | default `manual` | `manual` / `llm` / `import` |
| `status` | varchar(16) | default `active` | `active` / `disabled` |
| `note` | text | nullable | 备注 |
| `created_at` / `updated_at` | datetime | server_default now() | |

表级约束：

| 约束 | 名称 | 作用 |
|---|---|---|
| UNIQUE(`knowledge_point_id`,`prerequisite_id`) | `uq_knowledge_point_prerequisites_pair` | 同一对边不可重复 |
| CHECK(`knowledge_point_id <> prerequisite_id`) | `ck_knowledge_point_prerequisites_no_self_loop` | DB 级自环拦截 |

**模型注释明确区分**：`parent_id` = 归属层级（树），本表 = 前置依赖（DAG），二者不可互替。

---

## 四、服务层现状（`app/services/prerequisite.py`，402 行）

### 4.1 常量（唯一来源）

| 常量 | 值 | 含义 |
|---|---|---|
| `STRENGTH_MIN` / `STRENGTH_MAX` / `STRENGTH_DEFAULT` | 0 / 100 / **100** | 强度范围与默认 |
| **`BLOCKING_STRENGTH`** | **60** | **≥60 视为硬前置**：未满足时阻止学习后置 |
| `READY_THRESHOLD` | 70 | 前置被认为「已满足」所需的最低掌握度 |
| `UNKNOWN_MASTERY` | 0 | 从未作答 = 未满足（「未知」≠ 已掌握） |
| `MAX_TRAVERSAL_NODES` | 5000 | 防御性遍历上限 |
| `EDGE_SOURCES` | manual / llm / import | 来源枚举 |

### 4.2 关键机制

| 能力 | 方法 | 说明 |
|---|---|---|
| 本点依赖谁 | `list_for` | 按 strength 降序 |
| 谁依赖本点 | `list_dependents` | 反向查询（**无 HTTP 端点**） |
| 传递前置 | `prerequisite_closure` | BFS + visited，成环也不死循环 |
| 解锁数 | `unlock_count` | 传递后置计数 → **推荐 `unlock` 因子的唯一来源** |
| 拓扑序 | `topological_order` | 确定性（前置在前，同层按 id 升序） |
| 学习路径 | `learning_path` | closure + 拓扑序 + 目标 |
| 成环预判 | `would_create_cycle` | 目标已在候选的传递前置中 → 拒绝 |
| 写入校验链 | `add()` | ①两端存在 → ②**两端必须 concept**（`container` 一律拒） → ③自环 → ④重复 → ⑤成环；再 flush |

### 4.3 ⚠️ 对本次导入影响最大的机制（必须提前知道）

`app/services/recommendation.py` → `_learn_new_candidates()`：

```python
if knowledge_point_id in mastery_score:
    continue                      # 已作答过 → 不属"新知"
statuses = self.prerequisites.statuses_for(mastery_score, knowledge_point_id)
if any(status.blocking for status in statuses):
    continue                      # ← 硬前置未满足 → 该知识点完全不进「新知」候选
```

**含义**：`strength ≥ 60` 的边一旦落库，在用户掌握度未达标前，其 **target 会被整体排除出「新知」推荐**（不是降权，是直接不出现）。因此 strength 的取值不是「好看」，而是**直接决定新用户能看到多少可学内容**。

参考打分公式（不改动，仅用于预判）：
`score = BASE(learn_new=52) × urgency × gap(1+0.6×(100-ms)/100) × goal(1.25) × unlock(1+min(0.12×unlock_count, 0.6)) × recency`

---

## 五、API 现状

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/knowledge-points/{id}/prerequisites` | 登录用户 | 读前置 + 是否 satisfied / blocking |
| POST | `/knowledge-points/{id}/prerequisites` | **仅管理员** | 单条创建；body `{prerequisite_id, strength(0-100,默认100), note}` |
| DELETE | `/knowledge-points/{id}/prerequisites/{prerequisite_id}` | **仅管理员** | 单条删除（物理删除） |
| GET | `/knowledge-points/{id}/path` | 登录用户 | 学习路径（closure+拓扑序） |
| POST | `/knowledge-points/{id}/prerequisites/suggest` | **仅管理员** | LLM 提议，**只提议不落库** |

错误码映射（写入路径）：404 端点不存在 / 400 目录节点或自环或成环 / **409 重复**。

⚠️ **两处与「导入」相关的现状**：
1. **无批量端点**；
2. 写路径**硬编码 `source=EDGE_SOURCE_MANUAL`** → 经 API 写入的边无法标记为 `import`（`EDGE_SOURCE_IMPORT` 常量存在但**无调用方**）。

---

## 六、管理页现状（`web/src/components/PrerequisiteEditor.vue`，299 行）

| 已有能力 | 说明 |
|---|---|
| 前置列表 | 展示前置名、强度、`已满足 / 未满足（硬前置） / 未满足（软前置）` |
| 单条添加 | 下拉选择（**仅 concept**）+ 强度滑杆（0-100，**步长 10**）+ 备注 |
| 单条删除 | 逐条删除 |
| AI 提议 | 调 suggest → 展示「前置名 / 理由 / 置信度」，点「采纳」才写入（`note` 自动带 `AI 建议：…`） |
| 路径预览 | 内嵌展示该知识点学习路径（拓扑序 + 掌握度） |

| 缺失能力 | 影响 |
|---|---|
| ❌ 批量导入 UI（粘贴/CSV/多选） | 50 条需 50 次手工操作 |
| ❌ 审核状态机（草稿/待审/通过/驳回） | 无法在库内区分「已审核」与「未审核」 |
| ❌ 导入批次视图 | 无法按批次查看/回滚 |
| ❌ 下游（`list_dependents`）视图 | 与 M5 Step 2 记录的 G2 缺口一致 |

---

## 七、Step 0 五个确认项的回答

| # | 确认项 | 结论 |
|---|---|---|
| 1 | 当前 prerequisite 表结构 | 见第三节：`(id, knowledge_point_id, prerequisite_id, strength, source, status, note, created_at, updated_at)` + UNIQUE 对 + CHECK 自环 |
| 2 | `strength` 字段含义 | 0~100 的**依赖强度**；**≥60 = 硬前置（阻塞）**，<60 = 仅顺序建议。**不参与掌握度计算**，只参与「是否阻塞」与展示 |
| 3 | prerequisite 创建入口 | `POST /knowledge-points/{id}/prerequisites`（管理员，单条）；前端入口 = `PrerequisiteEditor`（管理员知识点弹窗内） |
| 4 | 是否支持批量导入 | ❌ **否**。无 batch 端点、无 CSV 入口、无导入批次表（对比：知识点导入有 `knowledge_point_import_batches`） |
| 5 | 是否已有审核机制 | ⚠️ **无独立审核机制**。现有「人审」是**操作层面**的：LLM 只提议不落库，管理员点「采纳/添加」才写入。库内**没有** pending/approved 状态字段（`status` 只有 active/disabled，且写路径恒为 active） |

---

## 八、能力缺口（本次不修，仅登记）

| 编号 | 缺口 | 影响本次导入 | 是否阻断 |
|---|---|---|---|
| G-A | 无批量写入端点 | 50 条需 50 次串行 POST | ❌ 不阻断（可脚本化） |
| G-B | 无 preview / dry-run 端点 | preview 只能在本地 + 只读 SQL 层做 | ❌ 不阻断 |
| G-C | 无导入批次记录表 | 回滚无法「按批次一键」，只能按显式清单逐条删 | ❌ 不阻断（本次边数少） |
| G-D | 写路径 `source` 恒为 `manual` | 无法用 `source='import'` 区分种子数据 | ❌ 不阻断（用 `note` 前缀替代） |
| G-E | `status='disabled'` 无写入方 | 无法「软停用」某条边，只能删除 | ❌ 不阻断 |

---

## 九、导入方案设计（**未执行**，待单独批准）

### 9.1 使用的 API

逐条调用**既有**接口（不新增任何后端 API）：

```
POST /knowledge-points/{target_id}/prerequisites
Authorization: Bearer <管理员 token>
Body: { "prerequisite_id": <source_id>, "strength": <strength>,
        "note": "M5 前置关系种子 | <reason>" }
```

- 权限：仅管理员（`get_current_admin`），生产管理员 uid=1；
- `note` 统一加 **`M5 前置关系种子` 前缀** → 既弥补 G-D（可检索来源），又提供**精准回滚抓手**；
- 写入顺序按「章节 → 层内 id」升序（不影响结果，便于中断后定位进度）。

### 9.2 是否需要 batch？

**结论：本次不需要新增 batch API，也不需要 migration。**

| 维度 | 评估 |
|---|---|
| 规模 | 50 条，串行 POST 秒级完成 |
| 可观测性 | 逐条返回码（201 / 400 / 409）**比批量端点更易定位**问题边 |
| 原子性 | 无。但前置边**彼此独立**（无外键关联其它表），部分失败不产生脏状态；中断即停止，已写入部分可逐条回滚 |
| 何时才需要 batch | 数据量 > 200 条、或需要「原子导入 + 批次回滚 + 导入审计表」时 → 属**后端改动 + 可能新增批次表（migration）**，须另行批准（建议留到 M6 或导入规模扩大后） |

### 9.3 回滚方案

| 层级 | 操作 | 说明 |
|---|---|---|
| 首选（应用层） | 对审核表 50 对 `(target_id, prerequisite_id)` 逐条 `DELETE /knowledge-points/{target}/prerequisites/{prereq}` | 复用既有 API，走服务层校验；恢复到 `edges=0` 基线 |
| 兜底（DB 层） | `DELETE FROM knowledge_point_prerequisites WHERE id IN (...)` | 仅在应用层不可用时使用，**绕过服务层，需单独批准** |
| 精准回滚抓手 | 按 `note LIKE 'M5 前置关系种子%'` 定位 | 不依赖记录清单是否完整 |
| 备份 | 执行前 `/backup/ai_study_<date>.sql` + 记录 **时间 / 路径 / 大小 / sha256** | 按发布协议执行（虽然本操作可逆） |

**回滚影响面**：本表**不被任何其它表外键引用**（无级联），删除边**不影响** 题目、掌握度、错题、答题记录。风险等级：**低**。

### 9.4 验证方案

| 时点 | 验证项 | 期望 |
|---|---|---|
| 导入前 | 只读 SQL 计数 | `edges=0` |
| 导入前 | 基线快照 | `GET /recommendations/today?limit=10` 与 `GET /knowledge-points/22/path` 结果留档（当前：推荐全同分、路径仅 1 节点） |
| 导入后 | 只读 SQL | `SELECT COUNT(*)` = **50**；抽样 3 条按 id 核对 strength/note |
| 导入后 | 应用层读接口 | `GET /knowledge-points/19/prerequisites` 返回「线性表的定义与基本操作 强度 80」 |
| 导入后 | 路径 | `GET /knowledge-points/22/path` 返回多节点链（线性表 → 栈 → 表达式求值） |
| 导入后 | 推荐 | `GET /recommendations/today?limit=10` 出现**多档分数**与含「前置…」`reason` |
| 反向 | 无环 | 取最深链（`图的存储结构 → DFS → 拓扑排序 → 关键路径`）逐级调 `/path`，应正常返回而非报错/超时 |

### 9.5 preview 流程（五步，含停止点）

```
1. 人工审核《M5_前置关系候选审核表.md》            ← 逐条签字（当前阶段，未签字）
2. 本地 dry-run 校验（已完成）                      ← 无环 / 两端 concept / 无重复 / 无 container
3. 生产只读 preflight                              ← 只读计数 + 记录基线快照（不发写请求）
4. 【停止点】用户单独批准写入
5. 写入 → 逐条校验 → 立即验证 → 出现异常即可按 9.3 回滚
```

---

## 十、影响预判（基于生产数据 + 真实打分公式）

### 10.1 候选集规模

| 方案 | 硬前置（≥60） | 零掌握度下可进「新知」推荐 | 被阻塞（不进推荐） |
|---|---|---|---|
| 现状（edges=0） | 0 | 56 | 0 |
| **建议方案（29 硬 / 21 软）** | 29 | **27** | 29 |
| 备选（50 条全硬） | 50 | **9**（仅章节根 + 1 个无前置节点） | 47 |

**建议 29 硬 / 21 软**：真正「不学就无法理解」的关系才设硬前置，其余（辅助理解、顺序建议）设 50 保持不阻塞，避免新用户可学范围被压缩到 9 个。

### 10.2 推荐分档（learn_new，零掌握度）

现状 `edges=0` → 所有 56 个 concept 的 `unlock` 因子恒为 1.0 → **分数完全相同**（公式基线 52×1.6 = 83.2；生产实测 5 条均 84.5，差异来自用户目标/计划命中）。

导入后（29 硬 / 21 软）：

| 档位 | unlock | 因子 | 分数 | 节点数 | 代表节点 |
|---|---|---|---|---|---|
| 1 | 13 / 12 / 9 / 6 | 1.60（封顶） | **133.12** | 4 | 线性表的定义与基本操作 / 树的基本概念与术语 / 图的基本概念与术语 / 排序的基本概念与稳定性 |
| 2 | 4 | 1.48 | 123.14 | 1 | 算法的定义与特性 |
| 3 | 2 | 1.24 | 103.17 | 3 | 时间复杂度分析 / 串的定义与存储结构 / 查找的基本概念与平均查找长度 |
| 4 | 1 | 1.12 | 93.18 | 3 | 数据结构基本概念 / 直接插入排序 / 冒泡排序 |
| 5 | 0 | 1.00 | 83.20 | 16 | 空间复杂度分析、顺序查找、归并排序… |

**分档数：1 档 → 5 档**（`unlock` 因子从「全局恒定」变为真实区分度来源）。

度分布：出度最大 = `图的存储结构`(6)、`线性表的定义与基本操作`(4)、`二叉树的定义与性质`(4)、`排序的基本概念与稳定性`(4)；入度最大 = 2（`KMP算法`、`顺序存储与链式存储的比较`、`折半查找`）—— 无「单点被过多前置依赖」的脆弱结构。

### 10.3 ⚠️ 已知局限（必须提前接受或另作决策）

| 局限 | 原因 | 影响 |
|---|---|---|
| **top-4 仍同分（133.12）** | `UNLOCK_CAP=0.6` 在 `unlock_count ≥ 5` 即封顶，4 个章节根都 ≥6 | 排序前 4 名并列；第 5 名起区分明显 |
| 唯一「合规」的消除办法 | 减少每章主干边数（牺牲图谱覆盖度），或引入新排序因子（**属算法改动，本次禁止**） | 建议：**接受**，由推荐解释（`reason`）承担区分（不同前置文案/解锁数量） |
| 29 个知识点暂不可推荐 | 硬前置未满足（用户掌握度=0） | 属**设计预期**；随答题积累逐级解锁。但需注意生产当前 `mastery=0`，解锁链条短期内不会推进 |

### 10.4 用户可见变化（导入后立即可见）

| 位置 | 变化 |
|---|---|
| `/my-plan` 区域 A | 不变（仍无掌握度记录） |
| `/my-plan` 区域 B | 推荐从「5 条同分 84.5」→「多档分数 + 含前置/解锁文案的 reason」 |
| `/my-plan` 区域 D | **学习路径从单节点 → 多节点时间线**（`path` = closure + 拓扑序），立即产生可视化内容 |
| `/knowledge` 详情 | 目标概念显示「前置知识 + 强度 + 已满足/未满足（硬/软）」 |
| `/questions` | 不变（仍 `mastery=0`，答题后才变化） |

---

## 十一、风险与决策点

| 编号 | 决策点 | 选项 | 建议 |
|---|---|---|---|
| D1 | 硬/软划分 | ① 29 硬 / 21 软（可推荐 27 个）② 50 条全硬（可推荐 9 个） | ✅ **①** |
| D2 | 是否接受 top-4 同分 | ① 接受（由 reason 区分）② 缩减扇出以拉开档位 | ✅ **①**（② 牺牲覆盖度且收益有限） |
| D3 | 是否需要后端改动 | ① 不需要（走单条 API）② 新增 batch + 批次表 | ✅ **①** |
| D4 | 是否需要 migration | ① 不需要 ② 新增导入批次表 | ✅ **①**（留待数据量扩大后） |
| D5 | `source` 无法标 `import` | 用 `note` 统一前缀 `M5 前置关系种子 · <reason>` 替代 | ✅ 采纳 |
| D6 | 是否同步处理「题目 ↔ 知识点关联」 | 生产 `questions=8`、关联与掌握度仍为空，是推荐 `review_*` 动作无法触发的另一数据缺口 | ⏸ **本阶段不做**（属 Step 5 / M6 议题，需另行批准） |

---

## 十二、本阶段边界（未做事项）

- ❌ 未调用任何**写**接口（`POST`/`DELETE` 前置边次数 = **0**）
- ❌ 未修改任何代码 / 配置 / 文档以外的文件
- ❌ 未创建 migration、未改数据库结构
- ❌ 未导入任何前置边（生产 `edges` 仍 = **0**）
- ❌ 未执行 production apply、未做备份（本次无写操作，无需备份）
- ❌ 未触碰 M6 / BKT / DeepKT / 推荐算法

> 另：M5 四份文档（含本文件）延续 Step 1–3 做法**未纳入 git**，待用户确认是否单独做 docs 提交。
