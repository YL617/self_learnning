# M5 Step 5 题目 ↔ 知识点关联现状审计

> 阶段：M5 Step 5「题目→知识点关联与真实学习闭环激活」· Step 0 只读分析
> 约束遵守：**未修改任何代码 / 未建 migration / 未调用任何写接口 / 未写入生产**；生产侧仅执行只读查询。
> 目的：确认 `question_knowledge_points`（qkp）的真实能力边界，给出 8 道题的绑定候选，并预判绑定后「答题 → mastery」闭环能否真正跑起来。
> 生成时间：2026-10-11 20:0x（GMT+8）｜ 本地 HEAD `62208e7`（= origin/main `f65e88e` 之后的三个本地前端提交，未推送）

---

## 一、结论速览

| 问题 | 结论 |
|---|---|
| qkp 表结构是否够用 | ✅ 够用，8 条绑定**零结构改动** |
| 创建入口 | ✅ 已有两处：`POST /admin/questions/{id}/knowledge-points`（管理员）、`POST /questions/{id}/knowledge-points`（owner/管理员），**均单条** |
| 是否支持批量导入 | ❌ 不支持（无 batch 端点、无批次表、无 CSV 导入） |
| 是否有审核机制 | ⚠️ 无独立审核状态机；「人审」= 本次人工逐题选定 concept（审核表即签字依据） |
| 是否需要后端修改 | ❌ **不需要**（8 条可经既有单条 API 完成） |
| 是否需要 migration | ❌ **不需要**（0 张新表、0 个新列、0 个约束变更） |
| 前端是否已有入口 | ✅ 已有 `QuestionKnowledgePointsModal`（挂在 `/questions` 用户端），管理员亦可手工点选 |
| 绑定后能否产生 mastery | ✅ **能**，且这是 qkp 唯一的 mastery 写入路径（见第四节因果链） |
| 本阶段是否写库 | ❌ 未写入；生产 `question_knowledge_points` 仍为 **0 行** |

---

## 二、生产实测基线（只读）

| 指标 | 实测值 |
|---|---|
| `knowledge_points` 总数 | **78** |
| ├ `concept`（可学习） | **56** |
| └ `container`（目录） | **22** |
| `knowledge_point_prerequisites`（前置边） | **50**（M5 Step 4 已 Apply） |
| **`question_knowledge_points`（题目↔知识点）** | **0** |
| `questions` | **8** |
| `user_knowledge_point_mastery`（掌握度） | **0** |
| `answer_records`（历史作答） | **4**（user 1：Q1 错、Q1 对、Q6 对、Q7 错） |
| `wrong_book_items` | **2** |
| `users` | 1（uid=1 = 管理员 YL617） |
| 题目学科分布 | 数据结构 ×8（`knowledge_points.subject` 亦全为「数据结构」→ **学科天然一致**） |

### 2.1 8 道题画像（`questions` 全量）

| Q id | 题型 | 现有 `knowledge_point`(自由文本) | `visibility` | `difficulty` | 题干摘要 | 答案 |
|---:|---|---|---|---|---|---|
| 1 | choice | 栈和队列 | private | NULL | 带头结点单链表实现链栈，入栈时新结点插入到哪个位置 | A |
| 2 | choice | 栈和队列 | private | NULL | 队列入队 a,b,c,d，哪个出队序列不可能出现 | B |
| 3 | choice | 栈和队列 | private | NULL | 大小 6 的数组实现循环队列，front=3/rear=5 时元素个数 | A |
| 4 | choice | 栈和队列 | private | NULL | 中缀表达式 `a + b * (c - d) - e / f` 转后缀是什么 | A |
| 5 | choice | 栈和队列 | private | NULL | 元素 a~e 经栈 S 出栈即入队 Q，出队序 c,e,d,b,a，栈 S 容量至少 | C |
| 6 | choice | 栈和队列 | private | NULL | 带头结点单链表链栈，出栈操作正确的是 | A |
| 7 | choice | 栈和队列 | private | NULL | 链栈已有 3 元素，再入栈 b、c 后栈顶元素是 | C |
| 8 | choice | 栈和队列 | private | NULL | 带头结点单链表链栈，判断栈空的条件是 | A |

> ⚠️ **`knowledge_point` 列 8 行全为「栈和队列」——是章名（container 语义），不是原子知识点**。这正是本阶段要做结构化绑定的直接原因：旧的自由文本列无法驱动 mastery，也不能被反查题目使用（`GET /knowledge-points/{id}/questions` 读的是 qkp）。
> `difficulty` 全为 NULL → 绑定的 effective 难度由 `evaluation.resolve_difficulty()` 按题型回落到 **easy**（choice=easy），mastery 增量按 easy 权重计算。

---

## 三、数据模型与写入校验链

`app/models/learning.py` → `QuestionKnowledgePoint`（表 `question_knowledge_points`）：

| 列 | 类型 | 约束 / 默认 | 说明 |
|---|---|---|---|
| `id` | int | PK | |
| `question_id` | int | FK→`questions.id` **CASCADE** | |
| `knowledge_point_id` | int | FK→`knowledge_points.id` **RESTRICT**，有索引 | |
| `role` | varchar(16) | default **`primary`** | `primary` / `secondary`（Schema Literal 校验） |
| `source` | varchar(16) | default **`manual`** | manual / ai / legacy / system |
| `kp_node_type` | varchar(16) | default **`concept`** | 恒为 concept |
| `created_at` | datetime | server_default now() | |

表级约束：

| 约束 | 名称 | 作用 |
|---|---|---|
| UNIQUE(`question_id`,`knowledge_point_id`) | `uq_question_knowledge_points_pair` | 同一对不可重复 |
| CHECK(`kp_node_type = 'concept'`) | `ck_qkp_kp_node_type` | 禁止 container |
| FK(`knowledge_point_id`,`kp_node_type`) → `knowledge_points(id,node_type)` | `fk_qkp_kp_concept` | **DB 级物理拒绝 container 关联** |

**写入校验链（`QuestionKnowledgePointService.attach()`，唯一写入路径）**：
`①题目存在 → ②知识点存在 → ③node_type 必须是 concept（否则 NotLearnableNode） → ④normalize_subject(question.subject) == kp.normalized_subject（否则 SubjectMismatch） → ⑤同一组合重复 → 幂等返回原行 → ⑥role=primary 且已有另一 primary → PrimaryConflict`。

> 关键：**mastery 的唯一写入源是「题目↔知识点关联」**。关住 `attach()` 的 concept 关口，就关住了 container 产生 mastery 的可能；任何未来写入路径只要复用本服务即自动被拦。因此本阶段**不应**、也**不需要**绕过服务层直写 DB。

### 3.1 API 现状

| 方法 | 路径 | 权限 | 说明 |
|---|---|---|---|
| GET | `/questions/{id}/knowledge-points` | owner/管理员 | 列出该题的关联 |
| POST | `/questions/{id}/knowledge-points` | owner/管理员 | attach 单条（body `{knowledge_point_id, role}`） |
| PUT | `/questions/{id}/knowledge-points` | owner/管理员 | replace 全量 |
| PATCH | `/questions/{id}/knowledge-points/{kp_id}` | owner/管理员 | set_primary |
| DELETE | `/questions/{id}/knowledge-points/{kp_id}` | owner/管理员 | detach（**唯一删除入口**） |
| GET | `/knowledge-points/{id}/questions` | 登录用户 | 反查题目（普通用户见自己+共享，管理员见全部） |
| POST | **`/admin/questions/{id}/knowledge-points`** | **仅管理员** | attach 单条（与用户端同一服务关口） |
| POST | `/admin/questions` | 仅管理员 | 建题时经 `knowledge_point_ids` 一并绑定（**仅建新题**，不适用存量 8 题） |

### 3.2 管理/用户端 UI 现状

| 端 | 能力 | 适用本次？ |
|---|---|---|
| `/questions`（用户端 `QuestionsView`） | 挂载 `QuestionKnowledgePointsModal`，可对**已有题目**逐个添加/切换关联 | ✅ 可行（uid=1 是全部 8 题的 owner） |
| `/admin/questions`（管理员端） | 建新题时多选绑定；详情仅**展示**已有绑定，**无**给存量题补绑的 UI | ⚠️ 存量题补绑需走 API |

---

## 四、因果链（本阶段的核心动因）

```
question_knowledge_points = 0
        │
        ▼
load_knowledge_point_signals(db, question_id) → ()     （evaluation.py:75）
        │
        ▼
build_evaluation(..., knowledge_points=()) → has_knowledge_points = False
        │
        ▼
MasteryService.apply_evaluation()
        └─► if not result.has_knowledge_points: return []   （mastery.py:277 提前 return）
        │
        ▼
user_knowledge_point_mastery 永远为 0
        │
        ├─► 推荐 review_weak / practice 动作无法触发（mastery=0 无「薄弱」可复）
        ├─► 学习路径 step.satisfied = (mastery ≥ 70) 恒 False → 前置永远「未满足」
        └─► mastery/summary 恒为空
  
（对照事实：生产已有 4 条 answer_records，但 mastery = 0 —— 因为作答时 qkp 为空，提前 return 已发生。）
```

**写入路径（绑定之后）**：
```
POST /api/v1/questions/{id}/answers
   └─► check_answer → AnswerRecord
   └─► _apply_learning_state()                       （questions.py:428）
         ├─ load_knowledge_point_signals()  ← 现在非空
         ├─ build_evaluation(..., knowledge_points=signals)
         └─ MasteryService.apply_evaluation()  → upsert user_knowledge_point_mastery
   └─► 同事务内：答对 → award_coins(+5)/pet_exp(+3)；答错 → WrongBookItem 新建/复习推进
```
→ **绑定 8 条 qkp 后，下一次作答即会真实写入 mastery。**

---

## 五、Step 5 需要的改动量

| 维度 | 结论 |
|---|---|
| 后端代码 | ❌ 0 改动（复用 `attach()` + 既有端点） |
| 数据库结构 | ❌ 0 改动（0 migration） |
| 前端代码 | ❌ 0 改动（现有 UI 可手工完成，或走 API） |
| **数据写入** | ✅ 8 条 `question_knowledge_points`（`source='manual'`、`role='primary'`） |
| 算法 | ❌ 不动（本阶段禁改推荐/掌握度算法） |

---

## 六、8 题绑定候选（详见《M5_Step5_题目知识点绑定候选表.md》）

8 道题全部属「栈和队列」章，按题干实际考查的原子知识点绑定到 4 个 concept：

| Q id | → concept（编码 / id / 名称） | 置信度 |
|---:|---|---|
| 1 | `DS.STACKQUEUE.STACK.BASIC` / 19 / 栈的定义与实现 | 高 |
| 2 | `DS.STACKQUEUE.QUEUE.BASIC` / 25 / 队列的定义与实现 | 高 |
| 3 | `DS.STACKQUEUE.QUEUE.CIRCULAR` / 26 / 循环队列 | 高 |
| 4 | `DS.STACKQUEUE.STACK.EXPRESSION` / 22 / 表达式求值 | 高 |
| 5 | `DS.STACKQUEUE.STACK.BASIC` / 19 / 栈的定义与实现 | 高 |
| 6 | `DS.STACKQUEUE.STACK.BASIC` / 19 / 栈的定义与实现 | 高 |
| 7 | `DS.STACKQUEUE.STACK.BASIC` / 19 / 栈的定义与实现 | 高 |
| 8 | `DS.STACKQUEUE.STACK.BASIC` / 19 / 栈的定义与实现 | 高 |

预校验（本地，未写库）：`count=8`｜`学科一致 = PASS`（全部 数据结构）｜`全部 concept = PASS`｜`每题唯一 primary = PASS`｜`(question_id,kp_id) 无重复 = PASS`。

---

## 七、覆盖度与影响预判

### 7.1 覆盖面（必须提前接受）

| 指标 | 值 |
|---|---|
| 绑定后「有题的知识点」 | **4** 个（19 / 22 / 25 / 26） |
| concept 覆盖率 | **4 / 56 = 7.1%** |
| 「栈和队列」章内 concept 覆盖 | 4 / 8（缺：括号匹配、栈与递归） |
| 集中度 | 5 / 8 题落在 `栈的定义与实现`（19） |

**→ 结论：绑定只会激活「4 个知识点」的 mastery。** 这是题目存量（8 题）决定的，不是绑定方案的问题。要扩大 mastery 覆盖，唯一路径是**增加题目**（另属 M6/题库建设议题），本阶段不做。

### 7.2 绑定后用户可见变化

| 位置 | 变化 |
|---|---|
| `/questions?knowledge_point_id=19` | 由「无题」→ 返回 5 道题（反查走 qkp，立即生效） |
| 推荐 `reason` | 若推荐命中 19/22/25/26，理由可带上「相关练习题 N 道」类信号（依既有实现） |
| `/mastery/summary` | 绑定本身**不变**（仍空）；**需一次真实作答**才出现记录 |
| 学习路径 `satisfied` | 绑定本身不变；作答后 19 等节点可能由未满足 → 部分/满足（阈值 70） |
| 旧自由文本列 `questions.knowledge_point` | **不变**（保持「栈和队列」，不删不改，兼容既有展示） |

### 7.3 已知局限（非缺陷）

| 局限 | 原因 | 影响 |
|---|---|---|
| mastery 只覆盖 4 个概念 | 只有 8 道题 | 多数知识点的 `satisfied` 仍恒 False |
| `review_weak`/`practice` 仍难触发 | 需 mastery < 60 且非空 | 只在 4 个概念上可能触发 |
| 历史 4 条作答**不会**追溯生成 mastery | `apply_evaluation` 只在作答时写入，非批量重算 | 需**新增一次真实作答**才能看到 mastery 记录（见 §9.3 决策点 D3） |

---

## 八、数据质量问题登记（不阻断绑定，建议另行处置）

只读检查 8 题 `analysis` 字段，发现 AI 生成解析存在**自相矛盾**（答案字母仍可作唯一评分依据，不影响绑定与打分）：

| Q id | 问题 | 性质 |
|---:|---|---|
| 2 | 解析先判定 B 不可能，又推断 C/D 亦不可能，最后「为符合单选强行选 B」 | 解析逻辑不自洽；题干在严格 FIFO 下存在多解缺陷 |
| 5 | 解析推导出「容量至少 3（应为 B）」，与题目答案 C 冲突，解析中出现「我修改解析」 | 解析与答案不一致 |

> 登记原因：你重视「数据质量 > 开发速度」。本阶段**只做绑定，不改题目内容**（改题干/答案属内容处置，需单独批准）。建议 M6 或题库治理专项处理。

---

## 九、导入方案设计（**未执行**，待单独批准）

### 9.1 使用的 API

逐条调用**既有**端点（不新增任何后端 API）：

```
POST /api/v1/admin/questions/{question_id}/knowledge-points
Authorization: Bearer <管理员 token（uid=1）>
Body: { "knowledge_point_id": <concept_id>, "role": "primary" }
```

- 权限：仅管理员（`get_current_admin`），生产管理员 uid=1，且 8 题 owner 均为 uid=1；
- `source` 由路由硬编码为 **`manual`**（qkp 无 `note` 列，也没有自定义 source 的入参）→ 回滚抓手改用**显式 pair 清单 + 当前表为空**这一事实（见 9.3）；
- 写入顺序按 Q id 升序，便于中断后定位进度。

### 9.2 是否需要 batch？

**结论：不需要新增 batch API，也不需要 migration。** 8 条串行 POST 秒级完成；逐条返回码（201/400/404）比批量端点更易定位问题。

### 9.3 回滚方案

| 层级 | 操作 | 说明 |
|---|---|---|
| 首选（应用层） | 对 8 对 `(question_id, knowledge_point_id)` 逐条 `DELETE /api/v1/questions/{id}/knowledge-points/{kp_id}`（Bearer uid=1） | 走服务层；恢复到 `qkp=0` 基线。**注意：管理员无 detach 端点，须用用户端 DELETE**（uid=1 是 owner，可用） |
| 兜底（DB 层） | `DELETE FROM question_knowledge_points WHERE id IN (...)` | 绕过服务层，**需单独批准** |
| 精准回滚抓手 | 执行前 `qkp = 0` → **本次写入的 8 行即为全表**，按 id 或 pair 清单删除即可 | 不依赖 note 前缀（该表无 note 列） |
| 备份 | 执行前 `/backup/ai_study_<date>.sql` + 记录 时间/路径/大小/sha256 | 按发布协议执行 |

**回滚影响面**：`question_knowledge_points` 被引用方 = 无（无其它表 FK 指向它）；删除关联**不影响**题目本身、答题记录、错题本。已产生的 mastery 行**不因删关联而回滚**（如需清空 mastery 需另批）。风险等级：**低**。

### 9.4 验证方案

| 时点 | 验证项 | 期望 |
|---|---|---|
| 导入前 | 只读 SQL | `qkp = 0`；`mastery = 0` |
| 导入前 | 基线快照 | `GET /recommendations/today?limit=10`、`GET /mastery/summary`、`GET /knowledge-points/19/questions` 留档 |
| 导入后 | 只读 SQL | `SELECT COUNT(*)` = **8**；`(question_id,kp_id)` 无重复；`role` 全 primary；`source` 全 manual；`kp_node_type` 全 concept |
| 导入后 | 应用层读接口 | `GET /knowledge-points/19/questions` 返回 5 条；`/22`、`/25`、`/26` 各 1 条 |
| 导入后 | 未变项 | `questions` 仍 8、`questions.knowledge_point` 文本未改、`mastery` 仍 0（未作答） |
| 闭环（若批准） | 真实作答 1 次 | 答对 → master 该 concept 上升、`mastery/summary` 出现记录、`/knowledge-points/19/path` 的 `satisfied` 可能翻转；答错 → 回落且 `weak` 计数变化 |
| 反查 | 权限 | `GET /knowledge-points/{id}/questions` 普通用户仅见自己+共享 |

> ⚠️ **闭环验证本身也是生产写入**（`answer_records` +1、`user_knowledge_point_mastery` upsert、可能新增 `wrong_book_items`、金币/宠物经验）。是否执行需你在 D3 明确。

### 9.5 导入前校验结果（本地 + 生产只读比对，**PASS 15/15**）

以生产容器内只读脚本比对「清单 vs 生产库」，全部通过：

| 检查项 | 结果 |
|---|---|
| `manifest.count == len(items)`（8 vs 8） | ✅ PASS |
| 无重复 `question_id` / 无重复 `(question_id,kp_id)` | ✅ PASS |
| 每题恰 1 个 item | ✅ PASS |
| 全部 `question_id` 在生产存在（missing=[]） | ✅ PASS |
| 全部 `knowledge_point_id` 在生产存在（missing=[]） | ✅ PASS |
| 目标全部 `node_type=concept`（bad=[]） | ✅ PASS |
| `knowledge_point_code` 与生产 code 一致（mismatch=[]） | ✅ PASS |
| 学科一致 `normalize_subject` 逐对匹配（mismatch=[]） | ✅ PASS |
| 无已存在的同 pair qkp 行（existing=[]） | ✅ PASS |
| `role` 全为 primary | ✅ PASS |
| 基线：`qkp=0` / `questions=8` / `mastery=0` / `prerequisites=50` | ✅ PASS |

```
PRE_IMPORT_CHECK: PASS
SUMMARY: {"checks": 15, "failed": 0}
```

### 9.6 preview 流程（含停止点）

```
1. 人工审核《M5_Step5_题目知识点绑定候选表.md》          ← 逐条签字（当前阶段，未签字）
2. 本地 dry-run 校验（已完成）                            ← 学科一致 / 全 concept / 每题唯一 primary / 无重复
3. 生产只读 preflight（已部分完成）                        ← 记录基线（qkp=0 / mastery=0 / 推荐快照）
4. 【停止点】你单独批准「绑定写入」与「闭环验证作答」
5. 写入 → 逐条校验 → 立即验证 → 异常即按 9.3 回滚
```

---

## 十、风险与决策点

| 编号 | 决策点 | 选项 | 建议 |
|---|---|---|---|
| D1 | 是否只绑 primary（不绑 secondary） | ① 每题 1 个 primary（8 条）② 额外给 4 道链栈题加 `单链表(13)` 作 secondary | ✅ **①**：最小必要；secondary 会让 mastery 部分外溢到 13，属新增语义，本阶段不引入 |
| D2 | 绑定写入是否现在执行 | ① 待你批准后执行 ② 现在执行 | ✅ **①**（按你的铁律：未经批准不改生产库） |
| D3 | 是否执行闭环验证作答 | ① 批准后在 Apply 阶段以 uid=1 真实作答 1~2 次验证闭环 ② 只绑定、不验证（待你日后手工在 UI 作答） | 待你定：① 证据最完整但会写 `answer_records`/`mastery`/`wrong_book`/金币；② 零副作用但闭环「未证」 |
| D4 | 是否用历史 4 条 `answer_records` 回填 mastery | ① 不回填 ② 新增回填脚本 | ✅ **①**：回填=重算历史，属新逻辑+额外写库，且违反「不伪造数据」；建议用 1 次真实作答替代证明 |
| D5 | 8 题覆盖面只有 4 个 concept 是否接受 | ① 接受（数据量决定）② 先扩题 | ✅ **①**：扩题属题库建设，本阶段不做 |
| D6 | 题目解析自相矛盾（Q2/Q5）是否本阶段修 | ① 不修，仅登记 ② 本阶段修 | ✅ **①**：改题属内容处置，需单独批准 |
| D7 | 是否需要后端/migration 改动 | ① 不需要 ② 需要 | ✅ **①** |

---

## 十一、本阶段边界（未做事项）

- ❌ 未调用任何**写**接口（qkp POST/DELETE 次数 = **0**）
- ❌ 未修改任何代码 / 配置 / migration
- ❌ 未改数据库结构
- ❌ 未写入任何 qkp 行（生产 `question_knowledge_points` 仍 = **0**）
- ❌ 未执行 production apply、未做备份（本次无写操作）
- ❌ 未改推荐/掌握度算法、未进入 M6、未建题、未回填 mastery
- ❌ 未修改 8 道题的题干/答案/解析

> 另：M5 各阶段文档延续既定做法**未纳入 git**，待你确认是否单独做 docs 提交。
