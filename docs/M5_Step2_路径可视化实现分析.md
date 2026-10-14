# M5 Step 2 · 学习路径可视化 —— 实现分析（只读确认）

- 文档类型：**只读实现分析（Implementation Analysis）** — 不含代码修改
- 编制日期：2026-10-11
- 继承基线：`docs/M5_Mastery架构审计.md`、`docs/M5_个性化学习系统设计方案.md`、Step 1 `/my-plan`（commit `e7049b6`）
- 本轮动作：**只读**（读取路径相关 API / schema / service / 前端消费模式 / `MyPlanView.vue`），**未修改任何文件**
- 停止规则：本阶段完成后停止，等待设计确认后再进入实现

---

## 0. 结论速览（TL;DR）

| 维度 | 结论 |
|---|---|
| 路径 API 是否够用 | ✅ **基本满足**：`GET /knowledge-points/{id}/path` 已返回「拓扑序前置链 + 目标」全套字段 |
| 是否需要后端改动 | ❌ **不需要**（0 后端改动、0 migration、0 新增 API） |
| 是否需要前端新 API 封装 | ❌ **不需要**（`knowledgePointsApi.learningPath(id)` 与 `LearningPath` TS 类型已存在） |
| 需要新增 | 1 个展示组件 + 1 个 spec |
| 需要修改 | `MyPlanView.vue`（+「我的学习路径」区域）+ `MyPlanView.spec.ts`（**必须**补 mock，见风险 R1） |
| **字段缺口（不改 API）** | ① 无「后续能力（下游）」② 无逐边 `strength`（影响"是否已解锁"的精确度）③ 无 `parent_id` 层级以外的直接前置标记 |

> **一句话**：路径数据后端已经备好，Step 2 是纯前端可视化，新增 1 组件 + 1 区域，复用既有 API 与类型。

---

## 1. 已有路径 API 是否满足需求

### 1.1 API 事实（真实代码）

| 项 | 内容 |
|---|---|
| 路由 | `backend/app/api/routes/knowledge_points.py:310-334` |
| 方法/路径 | `GET /api/v1/knowledge-points/{knowledge_point_id}/path` |
| 权限 | 登录用户（`Depends(get_current_user)`）→ **用户端可用** |
| 响应模型 | `LearningPathOut`（`backend/app/schemas/prerequisite.py:48-52`） |
| 服务 | `PrerequisiteService.learning_path()`（`backend/app/services/prerequisite.py:264-271`）= `prerequisite_closure`（传递前置，BFS+visited，上限 5000）+ `topological_order`（前置在前、同层 id 升序）+ 目标本身 |
| 阈值 | `READY_THRESHOLD = 70`（`prerequisite.py:42`）；`satisfied = mastery.get(id,0) >= 70` |
| 前端封装 | `knowledgePointsApi.learningPath(kpId)`（`web/src/api/knowledgePoints.ts` 已存在） |
| 前端类型 | `LearningPath` / `LearningPathStep` / `KnowledgePointBrief`（`web/src/types/index.ts:345-430` 已存在） |

### 1.2 需求逐条核对（Step 2 展示要求）

| 展示要求 | 是否满足 | 来源 |
|---|---|---|
| 节点名称 | ✅ | `step.knowledge_point.name` |
| 节点类型（concept / container） | ✅ | `step.knowledge_point.node_type` |
| 学习状态 | ✅ | `step.satisfied`（已满足 / 待掌握，阈值 70） |
| 掌握度（如有数据） | ✅ | `step.mastery_score`（`null` = 未作答） |
| 是否已解锁 | ⚠️ **近似** | 逐节点"解锁"需 `strength`（API 未下发）；采用派生近似（见 2.2） |
| 前置关系提示 | ⚠️ **部分** | 拓扑序链隐含顺序；精确直接前置需另调 `GET /{id}/prerequisites`（已有 API，可选） |
| 目标知识点 | ✅ | `step.is_target` + `path.target` |
| 目标是否可开始 | ✅ | `path.ready`（无硬前置阻塞） |
| 「后续能力（下游）」 | ❌ **无对应 API** | 服务层有 `list_dependents()`，但**无 HTTP 端点** → 本次不做（记录缺口） |

---

## 2. 返回字段 ↔ 前端展示字段映射

### 2.1 `LearningPath`（`GET /knowledge-points/{id}/path`）

| 后端字段 | 前端展示 |
|---|---|
| `target: KnowledgePointBrief` | 区域标题副文案「目标：{target.name}」 |
| `ready: bool` | 目标节点徽标：`ready ? '可开始' : '有待满足前置'` |
| `threshold: int`（70） | 说明文案「掌握度 ≥ 70 视为已满足」 |
| `steps[]` | 时间线节点序列（按 `order` 升序） |

### 2.2 `LearningPathStep`

| 后端字段 | 前端展示 | 说明 |
|---|---|---|
| `order` | 时间线序号（1..N） | 即「推荐学习顺序」 |
| `knowledge_point.name` | 节点名称 | — |
| `knowledge_point.node_type` | 类型徽标：`concept` → 「可学习」；`container` → 「目录（不可练习）」 | container 防御性展示（正常不会出现） |
| `knowledge_point.subject` | 学科文案 | 复用 `muted` 样式 |
| `knowledge_point.estimated_minutes` | 「约 N 分钟」（有值时） | 字段已在 Brief 中 |
| `knowledge_point.difficulty` | 难度徽标（有值时，可选） | easy/medium/hard |
| `mastery_score` | 掌握度条（复用 `MasteryBar`）或「未作答」 | `null` → 空态文案 |
| `satisfied` | 状态徽标：`已满足` / `待掌握` | 阈值 70 |
| `is_target` | 目标节点高亮 + 「目标」徽标 | — |

### 2.3 派生展示（**纯前端计算，不改后端**）

| 派生项 | 规则 | 备注 |
|---|---|---|
| 「当前知识点」 | 第一个 `satisfied === false` 的 step；若全为 true → 取 `is_target` 节点 | 表示"你应从这一步开始" |
| 「前置知识」 | `order` 小于目标步的所有 step | 即拓扑序中目标之前的链 |
| 「推荐学习顺序」 | `steps` 按 `order` 的原有顺序 | 后端已排好，前端不再排序 |
| 「是否已解锁」（近似） | 该 step 之前的所有 step 均 `satisfied` → 视为已解锁 | ⚠️ 近似：真实解锁只看 `strength ≥ 60` 的硬前置，而 API 未下发 `strength` |

---

## 3. 需要新增 / 修改的文件列表

### 3.1 新增（2）

| 文件 | 目的 |
|---|---|
| `web/src/components/LearningPathTimeline.vue` | 学习路径竖向时间线：节点名称 / 类型徽标 / 状态 / 掌握度 / 目标高亮 / 前置提示 |
| `web/src/components/LearningPathTimeline.spec.ts` | 覆盖：正常渲染、多节点顺序、concept/container 展示、空路径、加载态 |

### 3.2 修改（2，均为追加式）

| 文件 | 改动 | 兼容风险 |
|---|---|---|
| `web/src/views/MyPlanView.vue` | 在「推荐学习」区域**之后**追加区域「我的学习路径」：有数据→时间线；无目标→空态；请求中→加载态。新增 1 次只读调用 `knowledgePointsApi.learningPath(targetId)` | 🟢 低（追加区块，既有区域与逻辑不变） |
| `web/src/views/MyPlanView.spec.ts` | **必须**新增 `vi.mock('@/api/knowledgePoints')`（否则新增的调用会走真实 axios）+ 追加 2~3 例路径区域测试 | 🟢 低（既有 6 例需保持通过） |

### 3.3 明确不动

`RecommendationCard.vue`、`MasteryBar.vue`（仅复用）、`QuestionsView.vue`、`web/src/api/*`、`web/src/types/index.ts`、**全部后端代码 / 全部 migration / 全部 schema**。

---

## 4. 风险分析

| # | 风险 | 等级 | 说明与缓解 |
|---|---|---|---|
| R1 | `MyPlanView.spec.ts` 未 mock 新增 API | 🟡 中低 | 新增 `learningPath` 调用后，若 spec 不 mock，jsdom 下 axios 会真实发起请求（被 `Promise.allSettled` 吞掉，页面不报错，但测试语义脏）。**缓解：同步为 spec 增加 `knowledgePointsApi` mock**，并回归既有 6 例 |
| R2 | 「是否已解锁」语义近似 | 🟡 中低 | API 未下发逐边 `strength`，无法精确判定硬前置阻塞。**缓解：UI 文案用「已满足/待掌握」为主，解锁语义作为辅助提示；缺口记录在案（如需精确，可另调已有 `/prerequisites` 取目标直接前置的 `strength`/`blocking`）** |
| R3 | 目标知识点为 container | 🟢 极低 | 推荐候选仅 concept（`recommendation.py` 装载口已过滤），正常不会出现；组件仍做防御性展示（「目录（不可练习）」徽标） |
| R4 | 单节点路径（无前置） | 🟢 低 | `path.steps = [目标]` 属**正常**（后端 `learning_path` 对无前置点返回自身）。UI 显示单节点，不视为错误 |
| R5 | 无目标知识点（推荐为空） | 🟢 低 | 区域展示空态「暂无可展示的学习路径」，不影响其他区域（`Promise.allSettled` 隔离） |
| R6 | 请求 404 / 失败 | 🟢 低 | 与其它区域隔离；区域显示空态/错误提示，不白屏 |
| R7 | 样式偏离 | 🟢 低 | 复用既有 `card`/`badge`/`muted`/CSS 变量；**不引入任何 UI 框架** |

---

## 5. 测试计划

### 5.1 组件测试 `LearningPathTimeline.spec.ts`（5 例）

1. **正常路径渲染**：3 步链（前置A → 前置B → 目标）→ 名称/序号正确
2. **多节点顺序正确**：乱序传入 → 按 `order` 升序渲染
3. **concept / container 类型展示**：concept → 「可学习」；container → 「目录…不可练习」
4. **空路径状态**：`steps: []` → 空态文案，无节点
5. **加载状态**：`loading: true` → 加载文案，不展示空态

（另含断言：`is_target` 高亮、`mastery_score=null` → 未作答、`satisfied` 徽标文案）

### 5.2 页面测试 `MyPlanView.spec.ts`（追加 2~3 例）

- 路径区域渲染（mock `learningPath` 返回 3 步）
- 无目标（推荐为空）→ 路径区域空态
- 路径加载态

### 5.3 回归与门禁

| 检查 | 命令 | 期望 |
|---|---|---|
| 全量前端测试 | `npm test` | 25 → **26 文件**，201 → ≥208 用例，**全绿**（既有 201 例零破坏） |
| 类型检查 | `vue-tsc --noEmit` | 通过 |
| 构建 | `vite build` | 成功 |

### 5.4 提交

```
feat(web): M5 Step2 学习路径可视化
```
**仅本地 commit，不 push**（保持 `origin/main == 生产镜像 revision` 不变式）。

---

## 6. 待确认的决策点（批准后进入实现）

| # | 决策点 | 建议 |
|---|---|---|
| 1 | 「我的学习路径」目标知识点来源 | ✅ **默认 = 推荐列表第 1 条（order 最小）的知识点**；并在推荐列表每项追加「查看路径」以切换目标（复用 Step 1 自渲染列表，不动 `RecommendationCard`） |
| 2 | 「是否已解锁」精确度 | ✅ **采用派生近似 + 文案以「已满足/待掌握」为主**；不额外请求 `/prerequisites`（保持最小请求）。如你要求精确，可选增强：另调已有 `/prerequisites` 取目标直接前置 |
| 3 | 「后续能力（下游）」 | ✅ **本次不做**（无对应 API，需新增端点 → 超出 Step 2「不新增后端 API」约束）；记录为缺口，建议 M6 或后续 Step 评估 |
| 4 | 时间线视觉形态 | 建议：竖向 step 列表 + 连接线 + 状态徽标 + `MasteryBar`（紧凑模式）；与 `/my-plan` 现有卡片风格一致 |

---

**分析结论：Step 2 为纯前端可视化，复用 `GET /knowledge-points/{id}/path`（用户端可用、字段充足），需新增 1 组件 + 1 区域；0 后端改动、0 migration、0 新增 API。3 个字段缺口（下游/逐边 strength/直接前置标记）已记录，均不通过改 API 解决。等待设计确认后进入实现。**

```
M5 STEP 2 DESIGN ANALYSIS READY — 等待确认
```
