# M5 Step 5 · 题目 ↔ 知识点绑定 · Production Apply 验收报告

> 结论：**M5 STEP 5 PRODUCTION APPLY PASSED**（8 条 `primary` 绑定已落库并结构验证；闭环验证经独立测试账号实跑通过；测试数据已清理，生产回归基线 + 8 条绑定）
> 生成时间：2026-10-11（GMT+8）｜ 执行环境：生产 `https://yl617.xyz`

---

## 0. 基本信息

| 项 | 值 |
|---|---|
| 服务器 / 项目路径 | `root@8.136.194.163` / `/opt/ai-study` |
| git HEAD | `f65e88ee685127440dc9cc9dd3afcf65d27528f9` |
| 镜像 revision | `f65e88ee685127440dc9cc9dd3afcf65d27528f9`（== HEAD ✅） |
| alembic head | `20261010_007` |
| 容器状态 | backend(healthy) / web / redis(healthy) / mysql(healthy) |
| health | `GET /health` = 200 |
| 执行方式 | 逐条 REST（管理员 token uid=1）；**无批量 SQL 直写 qkp**、未绕过 API |
| 授权（用户 2026-10-11 20:26） | 8 条写入 ✅／闭环验证 ✅／清理 ✅；secondary ✗／历史回填 ✗／改 mastery ✗／改推荐 ✗／改题面 ✗ |

---

## 1. Step 0 · 生产前置状态（只读）

| 指标 | 值 | 指标 | 值 |
|---|---|---|---|
| `knowledge_points` | 78（concept 56 / container 22） | `question_knowledge_points` | **0** |
| `user_knowledge_point_mastery` | **0** | `questions` | 8 |
| `answer_records` | 4 | `wrong_book_items` | 2 |
| `knowledge_point_prerequisites` | 50（Step 4） | `users` | **1**（uid=1 YL617 / admin） |
| `user_profiles` | 1 | `coin_transactions` | 11 |
| `daily_stats` | 3 | `pets` | 1 |

- 8 道题**全部** `visibility=private`、`user_id=1`、`subject=数据结构`、`question_type=choice`、`difficulty=NULL`、`knowledge_point` 文本=「栈和队列」（章名，非原子知识点）。
- 目标 4 个 concept 均在位且 `node_type=concept`：`19 栈的定义与实现` / `22 表达式求值` / `25 队列的定义与实现` / `26 循环队列`。

---

## 2. Step 1 · 最终导入清单与导入前校验

- 最终清单：`docs/M5_Step5_题目知识点绑定清单.json`（`status=APPROVED`，8 条，`role=primary`）。
- 写入端点：`POST /api/v1/admin/questions/{question_id}/knowledge-points`，body `{"knowledge_point_id":<int>,"role":"primary"}`（服务端硬编码 `source="manual"`、`owner_id=None`）。

**`PRE_IMPORT_CHECK: PASS`（11/11 硬检查全通过）**

| 检查 | 结果 | 检查 | 结果 |
|---|---|---|---|
| C0 清单条数==8 | PASS | C6 code↔id 一致 | PASS |
| C1 每题 primary ≤1 | PASS | C7 学科一致（题 vs concept） | PASS |
| C2 无重复 (q,kp) pair | PASS | C8 无既有 pair 冲突 | PASS |
| C3 题目全部存在 | PASS | C9 基线 qkp==0 | PASS |
| C4 知识点全部存在 | PASS | C10 基线 mastery==0 | PASS |
| C5 目标全部 concept | PASS | C11 可见性（信息） | 8×private |

---

## 3. Step 2 · 写入明细（逐条 REST，一条一条）

| seq | question_id | knowledge_point_id | code | HTTP | created qkp id |
|---:|---:|---:|---|---:|---:|
| 1 | 1 | 19 | `DS.STACKQUEUE.STACK.BASIC` | 201 | 9 |
| 2 | 2 | 25 | `DS.STACKQUEUE.QUEUE.BASIC` | 201 | 10 |
| 3 | 3 | 26 | `DS.STACKQUEUE.QUEUE.CIRCULAR` | 201 | 11 |
| 4 | 4 | 22 | `DS.STACKQUEUE.STACK.EXPRESSION` | 201 | 12 |
| 5 | 5 | 19 | `DS.STACKQUEUE.STACK.BASIC` | 201 | 13 |
| 6 | 6 | 19 | `DS.STACKQUEUE.STACK.BASIC` | 201 | 14 |
| 7 | 7 | 19 | `DS.STACKQUEUE.STACK.BASIC` | 201 | 15 |
| 8 | 8 | 19 | `DS.STACKQUEUE.STACK.BASIC` | 201 | 16 |

- **ok=8 / fail=0，HTTP 201 ×8**；`role=primary`、`source=manual`、`kp_node_type=concept`。
- 说明：`question_knowledge_points.AUTO_INCREMENT` 起始为 9 → id 用 9–16（表曾被清空，历史 id 1–8 已消耗）。属既有痕迹，不影响正确性。

---

## 4. Step 3 · 结构验证

**`STRUCT_CHECK: PASS`**

| 检查 | 结果 | 检查 | 结果 |
|---|---|---|---|
| 总数 == 8 | ✅ | 无重复 (q,kp) | ✅ |
| 全部 `role=primary` | ✅ | 每题 primary 恰 1 | ✅ |
| 全部 `kp_node_type=concept` | ✅ | 无 container 目标 | ✅ |
| 全部 `source=manual` | ✅ | 绑定概念集 | `{19,22,25,26}` |

绑定后即时核对：`mastery=0`、`answer_records=4`、`users=1`（**未产生任何学习数据**，符合预期）。

---

## 5. Step 4 · 闭环验证（答错 → 答对）

### 5.1 前置阻断与决策

只读前置发现：① 8 题**全为 `private`**；② 生产**不存在测试用户**（`users=1`）；③ 系统**无「改题目可见性」或「管理端建用户」API**（`POST /admin/questions` 仅创建；`GET/PATCH /admin/users` 无创建）。→ 非管理员测试账号**无法作答**这些私题，构成真实阻断。

经用户选择 **方案 A**：新建独立测试账号 + 临时把 Q1 `visibility` 改 `shared`（一次性直连 DB 写，机制上无 API）→ 验证后还原并删除测试账号。

### 5.2 执行与证据

- 测试账号：`m5s5_verify_tmp` → **uid=4**（`role=user`；`POST /auth/register` HTTP 201）。注册仅生成 `users`+`user_profiles`。
- Q1 可见性：`private → shared`（记录在案，验证后还原）。
- 初始态（uid=4）：mastery / wrong_book / answer_records / coins / daily_stats / pets **全空**；`GET /mastery/summary = {total:0, weak_count:0, average_score:0.0}`。

**Case A · 答错**（Q1 答案 A，提交 `B`，`spent_seconds=15`）

| 观察项 | 结果 |
|---|---|
| `POST /questions/1/answers` | HTTP 201，`{id:7, is_correct:false}` |
| `GET /mastery/summary` | `{total:1, weak_count:1, average_score:42.0}` |
| `user_knowledge_point_mastery` | kp19：`score=42, attempt=1, correct=0, streak=0, last_correct_at=NULL` |
| `wrong_book_items` | 新增 1 条（Q1，`review_stage=1, review_count=0, mastered=0`） |
| `coin_transactions` | 无 | 
| `daily_stats` | 新建：`answered=1, correct=0, coins=0` |
| `pets` | 新建：`exp=3` |

**Case B · 答对**（同一 Q1，提交 `A`，`spent_seconds=8`）

| 观察项 | 结果 |
|---|---|
| `POST /questions/1/answers` | HTTP 201，`{id:8, is_correct:true}` |
| `GET /mastery/summary` | `{total:1, weak_count:1, average_score:54.0}` |
| `GET /mastery`（列表） | kp19：`score=54, attempt=2, correct=1, streak=1`，`last_reviewed_at` 已置 |
| `wrong_book_items` | 同一行 `review_count 0→1`、`review_stage 1→2`、`mastered` 仍 0 |
| `coin_transactions` | +1 条：`+5 答对题目` |
| `daily_stats` | `answered=2, correct=1, coins=5` |
| `pets` | `exp 3→6` |

### 5.3 算法预测 vs 实测（确定性算法复算）

| 步骤 | 公式复算 | 预期 | 实测 | 判定 |
|---|---|---|---|---|
| Case A | `50 − 14×0.8×(0.35+0.65×50/100)` = `50−7.56` | 42 | **42** | ✅ |
| Case B | `42 + 16×(0.8×1.0×1.25)×(0.35+0.65×58/100)` = `42+11.63` | 54 | **54** | ✅ |

> 权重：choice→`easy`(0.8) × primary(1.0) × 复习系数(1.25)；`GAIN_BASE=16 / LOSS_BASE=14 / HEADROOM_FLOOR=0.35`。

### 5.4 推荐侧联动（闭环最末环）

把推荐候选上限临时放行观察（**排序逻辑不变**，仅用于观察排名）：全量 **29 个候选**中，kp19 的 `review_weak` **已作为真实候选生成**，排名第 **12**：

```
review_weak  kp=19  栈的定义与实现  score=74.97
  components = {base:72.0, urgency:1.0, gap:1.276, goal:1.0, unlock:1.36, recency:0.6}
  reason = 掌握度 54%，低于薄弱线 60%；最近 2 次作答错了 1 次；已作答 2 次；学会它可以解锁 3 个后续知识点
```

- 复算：`72 × 1.276 × 1.36 × 0.6 = 74.97` ✅。
- **未进默认 Top10 的原因**：`recency=0.6`（刚作答过 → 设计内降权）+ 55 个 `learn_new` 候选竞争。**属设计行为，非缺陷**。
- `< 60` 且 `attempt≥1` 的知识点从此进入 `review_weak` 候选集 —— 这正是 Step 5 要激活的「推荐变化」。

---

## 6. Step 5 · 清理与最终基线核对

**清理**（uid=4，先全表扫描引用，逐表精确删除）：

| 表 | 删除行数 | 表 | 删除行数 |
|---|---:|---|---:|
| `answer_records` | 2 | `user_knowledge_point_mastery` | 1 |
| `coin_transactions` | 1 | `user_profiles` | 1 |
| `daily_stats` | 1 | `wrong_book_items` | 1 |
| `pets` | 1 | `users`（本体） | 1 |

残留复查：上述各表对 uid=4 计数 **全 0**。Q1 可见性 **`shared → private`**（8 题恢复全 private）。

**最终基线 vs 前置（唯一差异 = 本次绑定）**

| 指标 | 前置 | 最终 | 判定 |
|---|---:|---:|---|
| `question_knowledge_points` | 0 | **8** | ✅ 唯一预期变化 |
| `knowledge_points`（56/22） | 78 | 78 | ✅ |
| `user_knowledge_point_mastery` | 0 | 0 | ✅ |
| `questions`（全 private） | 8 | 8 | ✅ |
| `answer_records` | 4 | 4 | ✅ |
| `wrong_book_items` | 2 | 2 | ✅ |
| `knowledge_point_prerequisites` | 50 | 50 | ✅ |
| `users` / `user_profiles` | 1 / 1 | 1 / 1 | ✅ |
| `coin_transactions` / `daily_stats` / `pets` | 11 / 3 / 1 | 11 / 3 / 1 | ✅ |
| `alembic head` | 20261010_007 | 20261010_007 | ✅ |

---

## 7. 回滚方案

| 层级 | 操作 | 说明 |
|---|---|---|
| 首选（逐条，走 API） | `DELETE /api/v1/questions/{qid}/knowledge-points/{kp}`（Bearer 管理员 token） | 管理员 `owner_id=None`，`detach` 语义可达；本阶段**未实测**（未发生回滚需求），端点与 owner 语义已代码核对 |
| 兜底（SQL） | `DELETE FROM question_knowledge_points WHERE id IN (9..16)` | 绕过服务层，需单独批准 |
| 基线 | 执行前 `question_knowledge_points = 0` | 清空即完全回滚（无外键指向本表、无 migration 影响） |
| 影响的表 | 仅 `question_knowledge_points` | 不影响题目/掌握度/错题/前置边 |

---

## 8. 未做事项（边界）

❌ 未引入 `secondary`（含 4 道链栈题到 单链表(13)）｜❌ 未回填历史 mastery（历史 4 条 `answer_records` 不回溯）｜❌ 未改 mastery / 推荐算法｜❌ 未改题干/答案/解析｜❌ 未新增题目｜❌ 未改任何 schema / migration｜❌ 未启动 worker/beat｜❌ 未触碰 M6 / BKT / DeepKT｜❌ 未保留任何测试账号或验证数据（已 100% 清理）。

---

## 9. 遗留观察与建议（不属本次改动，供后续决策）

1. **「无真实学习数据」的结构性原因不止 `qkp=0`**：8 题**全为 admin 私题**，任何非管理员用户**根本无法作答**。即使 qkp 已补齐，只要题目仍是私题，真实 mastery 数据仍无法从真实用户产生。→ 建议后续单列议题：**题库共享策略（private/shared）**。
2. **覆盖面有限**：绑定仅覆盖 **4/56 = 7.1%** 的 concept，且 5/8 题集中于「栈的定义与实现」(kp19)。要扩大 mastery 覆盖只能**加题**（属题库建设 / M6，本阶段不做）。
3. **`AUTO_INCREMENT` 痕迹**：qkp 起始 9、新用户 id=4 → 表/序列曾有历史插入后被清空。非缺陷，仅记录。
4. **推荐 `recency` 降权**：刚练过的薄弱点会被 0.6 倍降权，短时间内不进 Top10。若产品希望「刚做错立即提醒」，需调推荐策略（**本阶段禁改算法**）。
5. 主机内存 1.6GiB，本次仅轻量只读/单点写入，无 OOM 迹象。
