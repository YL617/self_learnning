# M5 Step 3 实施前确认（只读）

> 范围：推荐解释增强 + 推荐→知识点→练习闭环。
> 约束：不改后端、不建 migration、不改推荐算法、不新增后端 API（除非发现闭环缺口，须先停止并报告）。
> 本文档仅为只读确认结论，**不含任何代码修改**。

---

## 一、五个确认项

### 1. 推荐卡片当前字段

后端 `app/schemas/recommendation.py` → `RecommendationOut`（前端 `RecommendationItem` 一一对应）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `action` / `action_label` | `review_wrong` \| `review_weak` \| `learn_new` \| `practice` / string | 动作类型与中文标签 |
| `knowledge_point_id` / `knowledge_point_name` | int / string | 知识点标识与名称 |
| `subject` | string | 学科 |
| `score` | float | 综合分（BASE×urgency×gap×goal×unlock×recency） |
| **`reason`** | string | **推荐理由，后端已生成、以「；」拼接多因子** |
| `order` | int | 排序位次 |
| `estimated_minutes` | int | 预计用时 |
| `components` | `dict[str, float]` | 打分分解项（base/urgency/gap/goal/unlock/recency） |
| `question_ids` | `list[int]` | 关联题目 id（错题类动作用） |

**结论：`reason` 与 `components` 均已存在** → Step 1「推荐理由增强」不需要任何后端改动，也不需要在后端拼文案。
后端 reason 现有模板（`services/recommendation.py`）已包含：「掌握度 X%，低于薄弱线 60%」「最近 N 次作答错了 M 次」「学会它可以解锁 N 个后续知识点」「前置 X 掌握度 Y%，已满足开始条件」「没有前置知识点，可以直接开始」等。

### 2. 当前点击行为

| 位置 | 现状 |
|---|---|
| `RecommendationCard.vue`「开始」 | `emit('start', item)` → 由父页面（Dashboard）决定去向 |
| `MyPlanView.vue`「去练习」 | `router.push({ name:'questions', query:{ knowledge_point_id } })`（**Step 1 已携带 query，目标页尚未消费**） |
| `MyPlanView.vue`「查看知识点」 | `router.push({ name:'knowledge', query:{ knowledge_point_id } })`（**同上，尚未消费**） |
| `MyPlanView.vue`「查看路径」 | 页内切换路径目标（Step 2 已完成） |

**结论：两个跳转都已携带 `knowledge_point_id`，缺口只在「目标页不读取」。**

### 3. 知识点详情入口

- 路由：`/knowledge` → `name: 'knowledge'` → `KnowledgeExploreView.vue`（左树 + 右详情）。
- 现状：`onMounted(load)` 只加载全量知识点，**不读 `route.query`**（全文无 `useRoute`）。
- 详情面板已具备：名称、编码、描述、难度、预计用时、**关联题目数**、**掌握度条（MasteryBar）**、作答/正确/连胜统计、**关联题目列表（QuestionCard，可直接作答）**。
- `container` 节点有双保险拒绝进详情（前端 `selectConcept` + 后端 DB 级约束）。

**结论：详情面板已有「基本信息 + mastery + 练习入口」三要素，只差按 query 自动定位选中。**

### 4. 练习入口是否已有

已有，且不止一个：

| 入口 | 位置 | 说明 |
|---|---|---|
| 直接作答 | `KnowledgeExploreView` 详情面板内 `QuestionCard` | 按知识点列出关联题目，点击即可答题 |
| 智能练习页 | `/questions` → `QuestionsView.vue` | 结构化知识点筛选器（`KnowledgePointSelector`）+ 掌握度 + 前置提示 + 生成题目；`generate` 已支持 `knowledge_point_id` |

- `GET /knowledge-points/{id}/questions`（只读，`knowledgePointsApi.questions`）返回该知识点已关联题目。
- `POST /questions/{id}/answers` 为唯一答题入口；`GET /questions` 为题目列表。

**结论：练习链路 100% 已存在，Step 3 只需把 query 接通。**

### 5. 答题后 mastery 是否自动更新

**是，且是同一事务。** `app/api/routes/questions.py` → `submit_answer`：

```
check_answer → 写 AnswerRecord → award_coins → _apply_learning_state(mastery/错题/复习排期)
             → award_pet_exp → record_daily_stat → db.commit()   # 单一事务，失败整体回滚
```
- 事务语义：掌握度、错题/复习状态与答案必须同时成功或同时失败；异常一律 rollback 并返回 500，不产生「答案已存但掌握度没更新」的半完成态。
- 前端：`KnowledgeExploreView.onAnswered()` / `QuestionsView.onAnswered()` 已在答题后局部刷新掌握度。

**结论：闭环最后一环（答题 → mastery 变化）无需改动。**

---

## 二、闭环完整性判定

```
推荐（GET /recommendations/today  ✅已有）
  ↓ 理由（item.reason / item.components  ✅已有）
  ↓ 进入知识点（MyPlanView 已携带 query  ⚠️目标页未消费）
  ↓ 开始练习（QuestionsView 筛选器 + KnowledgePointSelector  ✅已有，⚠️未消费 query）
  ↓ 答题（POST /questions/{id}/answers  ✅已有）
  ↓ mastery 更新（_apply_learning_state 同事务  ✅已有）
```

**缺口 = 2 个前端读取动作**，不涉及任何后端接口缺失 → **无需触发「停止并报告」条件**，无需新增后端 API。

---

## 三、改动清单（Step 3 实施）

### 新增（2）

| 文件 | 目的 |
|---|---|
| `web/src/components/RecommendationReason.vue` | 推荐理由展示组件：多因子逐条展示、无理由空态、`components` 折叠「打分依据」 |
| `web/src/components/RecommendationReason.spec.ts` | 覆盖：有 reason / 无 reason / 多因子 / 空状态（item 为 null） |

### 修改（5，全部追加式）

| 文件 | 改动 | 兼容风险 |
|---|---|---|
| `web/src/views/MyPlanView.vue` | 用 `RecommendationReason` 替换内联「推荐理由：…」文本（保留 `.plan-rec-reason` class，样式与既有断言不变） | 🟢 低 |
| `web/src/views/KnowledgeExploreView.vue` | 读 `route.query.knowledge_point_id`：自动展开祖先、切换学科、定位选中该 concept | 🟡 中低（需同步补 spec 的 router mock） |
| `web/src/views/QuestionsView.vue` | 读 `route.query.knowledge_point_id`：预填筛选 + 拉取该知识点已关联题目（只读）+ 掌握度/前置提示；无 query 行为完全不变 | 🟡 中低（同上） |
| `web/src/views/KnowledgeExploreView.spec.ts` | 追加 router mock + 1 个 query 定位用例（既有 5 例保持通过） | 🟢 低 |
| `web/src/views/QuestionsView.spec.ts` | 追加 router mock + `knowledgePointsApi.questions` mock + 2 个 query 用例（既有 9 例保持通过） | 🟢 低 |

### **明确不动**

`RecommendationCard.vue`、`MasteryBar.vue`、`QuestionCard.vue`、`api/*`、`types/*`、`router/index.ts`、`DefaultLayout.vue`，以及**全部后端代码 / 全部 migration**。

---

## 四、风险分析

| 编号 | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | 两个既有 view 新增 `useRoute()`，其 spec 未 mock `vue-router` → 既有用例报「No active route」 | 🟡 中 | 实施时同步补 router mock；`MyPlanView.spec.ts` 已有可复用写法 |
| R2 | `KnowledgeExploreView` 自动定位需先展开祖先并切换学科，否则目标行 `display:none` | 🟡 中低 | 定位前先从 `collapsed` 中移除全部祖先 + 对齐 `subject` |
| R3 | `QuestionsView` 用该知识点题目替换列表 → 可能改变「生成后列表」语义 | 🟢 低 | 仅在 query 存在时生效；无 query 分支代码路径不动 |
| R4 | query 值非法（非数字/不存在/container） | 🟢 低 | 非法直接忽略；不存在不选中；container 按既有规则拒绝 |
| R5 | 误改推荐算法 / 后端 | 🟢 低 | 本轮不打开后端文件；仅前端两处读 query |

---

## 五、测试计划

| 层 | 命令 | 目标 |
|---|---|---|
| 定向 | `npx vitest run <新增/受影响 spec>` | 新增用例全绿 |
| 全量 | `npm test` | 基线 26 文件 / 212 用例 → **0 破坏**，用例数只增不减 |
| 类型 | `vue-tsc --noEmit` | 通过 |
| 构建 | `vite build` | 通过 |

新增用例覆盖：推荐理由（有/无/多因子/空态）、知识点页 query 自动定位、练习页 query 预填 + 拉取关联题目 + 异常降级。
