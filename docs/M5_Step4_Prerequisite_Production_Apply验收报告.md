# M5 Step 4 · Prerequisite Production Apply 验收报告

> 对象：生产 **ai-study**（https://yl617.xyz ｜ root@8.136.194.163 ｜ `/opt/ai-study`）
> 范围：将已人工审核通过的 **50 条**前置关系写入生产 `knowledge_point_prerequisites`（M5 首次写入影响学习逻辑的数据）。
> 结论：**M5 STEP 4 PRODUCTION APPLY PASSED**

## 0. 预检（Step 0 · 只读）

| 项 | 期望 | 实测 | 结果 |
|---|---|---|---|
| /health | 200 | 200 | ✅ |
| 容器 | backend/web/redis/mysql healthy | backend(healthy)/web(Up)/redis(healthy)/mysql(healthy) | ✅ |
| git HEAD（服务器） | f65e88e | f65e88ee685127440dc9cc9dd3afcf65d27528f9 | ✅ |
| 镜像 revision | == git HEAD | f65e88ee685127440dc9cc9dd3afcf65d27528f9 | ✅ |
| alembic | 20261010_007 (head) | 20261010_007 (head) | ✅ |
| knowledge_points | 78 (concept 56 / container 22) | 78 (56/22) | ✅ |
| prerequisite edges（写入前） | 0 | 0 | ✅ |

## 1. Apply 时间

- 执行：2026-10-11 19:30:49 (GMT+8) / 2026-10-11T11:30:49Z (UTC)
- 验证采样：2026-10-11T11:32:18Z（UTC）/ 19:32（GMT+8）

## 2. 导入文件 SHA256

```
93fc9ed7c6a4cacded115e231133ce26bad0c692dbf44807705b6ecebc71d0fd  docs/M5_前置关系导入清单.json
```

## 3. 写入数量

| 项 | 值 |
|---|---|
| 清单条目 | 50 |
| 生产 `knowledge_point_prerequisites` | **50** |
| 写入方式 | 逐条 `POST /api/v1/knowledge-points/{target_id}/prerequisites`（管理员 token） |
| 禁止项遵守 | 未批量 SQL 直写 / 未绕过 API / 未自动补边 |

## 4. 成功/失败数量

| 结果 | 数量 |
|---|---|
| HTTP 201（成功） | **50** |
| 失败 | **0** |
| edge id 区间 | 1 – 50 |

## 5. edge id 映射表

| # | source_code（前置） | target_code（后置） | source_id | target_id | strength | edge_id | status |
|---|---|---|---|---|---|---|---|
| 1 | `DS.BASIC.CONCEPT` | `DS.BASIC.ADT` | 2 | 3 | 80 | 1 | 201 |
| 2 | `DS.LINEAR.CONCEPT` | `DS.LINEAR.SEQUENTIAL` | 9 | 11 | 80 | 2 | 201 |
| 3 | `DS.LINEAR.CONCEPT` | `DS.LINEAR.LINKED_LIST.SINGLE` | 9 | 13 | 80 | 3 | 201 |
| 4 | `DS.LINEAR.CONCEPT` | `DS.STACKQUEUE.STACK.BASIC` | 9 | 19 | 80 | 4 | 201 |
| 5 | `DS.LINEAR.CONCEPT` | `DS.STACKQUEUE.QUEUE.BASIC` | 9 | 25 | 80 | 5 | 201 |
| 6 | `DS.LINEAR.LINKED_LIST.SINGLE` | `DS.LINEAR.LINKED_LIST.DOUBLE` | 13 | 14 | 80 | 6 | 201 |
| 7 | `DS.LINEAR.LINKED_LIST.SINGLE` | `DS.LINEAR.LINKED_LIST.CIRCULAR` | 13 | 15 | 80 | 7 | 201 |
| 8 | `DS.STACKQUEUE.STACK.BASIC` | `DS.STACKQUEUE.STACK.MATCHING` | 19 | 21 | 90 | 8 | 201 |
| 9 | `DS.STACKQUEUE.STACK.BASIC` | `DS.STACKQUEUE.STACK.EXPRESSION` | 19 | 22 | 90 | 9 | 201 |
| 10 | `DS.STACKQUEUE.STACK.BASIC` | `DS.STACKQUEUE.STACK.RECURSION` | 19 | 23 | 50 | 10 | 201 |
| 11 | `DS.STACKQUEUE.QUEUE.BASIC` | `DS.STACKQUEUE.QUEUE.CIRCULAR` | 25 | 26 | 80 | 11 | 201 |
| 12 | `DS.STRING.BASIC` | `DS.STRING.BF` | 28 | 29 | 80 | 12 | 201 |
| 13 | `DS.TREE.CONCEPT` | `DS.TREE.BINARY.BASIC` | 32 | 34 | 80 | 13 | 201 |
| 14 | `DS.TREE.BINARY.BASIC` | `DS.TREE.BINARY.STORAGE` | 34 | 35 | 80 | 14 | 201 |
| 15 | `DS.TREE.BINARY.BASIC` | `DS.TREE.BINARY.TRAVERSAL` | 34 | 36 | 80 | 15 | 201 |
| 16 | `DS.TREE.BINARY.BASIC` | `DS.TREE.HEAP` | 34 | 38 | 80 | 16 | 201 |
| 17 | `DS.TREE.BINARY.BASIC` | `DS.SEARCH.BST` | 34 | 63 | 80 | 17 | 201 |
| 18 | `DS.TREE.BINARY.TRAVERSAL` | `DS.TREE.BINARY.THREADED` | 36 | 37 | 90 | 18 | 201 |
| 19 | `DS.TREE.HEAP` | `DS.TREE.PRIORITY_QUEUE` | 38 | 39 | 80 | 19 | 201 |
| 20 | `DS.GRAPH.CONCEPT` | `DS.GRAPH.STORAGE` | 45 | 46 | 80 | 20 | 201 |
| 21 | `DS.GRAPH.STORAGE` | `DS.GRAPH.DFS` | 46 | 48 | 90 | 21 | 201 |
| 22 | `DS.GRAPH.STORAGE` | `DS.GRAPH.BFS` | 46 | 49 | 90 | 22 | 201 |
| 23 | `DS.GRAPH.STORAGE` | `DS.GRAPH.SHORTEST_PATH.DIJKSTRA` | 46 | 55 | 80 | 23 | 201 |
| 24 | `DS.GRAPH.DFS` | `DS.GRAPH.TOPOLOGICAL_SORT` | 48 | 57 | 80 | 24 | 201 |
| 25 | `DS.GRAPH.TOPOLOGICAL_SORT` | `DS.GRAPH.CRITICAL_PATH` | 57 | 58 | 90 | 25 | 201 |
| 26 | `DS.SEARCH.BST` | `DS.SEARCH.AVL` | 63 | 64 | 90 | 26 | 201 |
| 27 | `DS.BASIC.ALGORITHM` | `DS.BASIC.COMPLEXITY.TIME` | 4 | 6 | 50 | 27 | 201 |
| 28 | `DS.BASIC.ALGORITHM` | `DS.BASIC.COMPLEXITY.SPACE` | 4 | 7 | 50 | 28 | 201 |
| 29 | `DS.LINEAR.SEQUENTIAL` | `DS.LINEAR.COMPARISON` | 11 | 16 | 50 | 29 | 201 |
| 30 | `DS.LINEAR.SEQUENTIAL` | `DS.SEARCH.BINARY` | 11 | 62 | 50 | 30 | 201 |
| 31 | `DS.LINEAR.LINKED_LIST.SINGLE` | `DS.LINEAR.COMPARISON` | 13 | 16 | 50 | 31 | 201 |
| 32 | `DS.TREE.CONCEPT` | `DS.TREE.FOREST.CONVERSION` | 32 | 41 | 50 | 32 | 201 |
| 33 | `DS.TREE.BINARY.TRAVERSAL` | `DS.TREE.FOREST.TRAVERSAL` | 36 | 42 | 50 | 33 | 201 |
| 34 | `DS.TREE.BINARY.TRAVERSAL` | `DS.TREE.HUFFMAN` | 36 | 43 | 50 | 34 | 201 |
| 35 | `DS.GRAPH.STORAGE` | `DS.GRAPH.MST.PRIM` | 46 | 52 | 50 | 35 | 201 |
| 36 | `DS.GRAPH.STORAGE` | `DS.GRAPH.MST.KRUSKAL` | 46 | 53 | 50 | 36 | 201 |
| 37 | `DS.GRAPH.STORAGE` | `DS.GRAPH.SHORTEST_PATH.FLOYD` | 46 | 56 | 50 | 37 | 201 |
| 38 | `DS.SEARCH.BASIC` | `DS.SEARCH.HASH` | 60 | 65 | 50 | 38 | 201 |
| 39 | `DS.STRING.BF` | `DS.STRING.KMP` | 29 | 30 | 90 | 39 | 201 |
| 40 | `DS.TREE.HEAP` | `DS.SORT.SELECTION.HEAP` | 38 | 76 | 90 | 40 | 201 |
| 41 | `DS.SORT.INSERTION.DIRECT` | `DS.SORT.INSERTION.SHELL` | 69 | 70 | 80 | 41 | 201 |
| 42 | `DS.BASIC.COMPLEXITY.TIME` | `DS.STRING.KMP` | 6 | 30 | 50 | 42 | 201 |
| 43 | `DS.BASIC.COMPLEXITY.TIME` | `DS.SORT.COMPARISON` | 6 | 78 | 50 | 43 | 201 |
| 44 | `DS.LINEAR.SEQUENTIAL` | `DS.SEARCH.SEQUENTIAL` | 11 | 61 | 50 | 44 | 201 |
| 45 | `DS.SEARCH.BASIC` | `DS.SEARCH.BINARY` | 60 | 62 | 50 | 45 | 201 |
| 46 | `DS.SORT.BASIC` | `DS.SORT.INSERTION.DIRECT` | 67 | 69 | 50 | 46 | 201 |
| 47 | `DS.SORT.BASIC` | `DS.SORT.SWAP.BUBBLE` | 67 | 72 | 50 | 47 | 201 |
| 48 | `DS.SORT.BASIC` | `DS.SORT.SELECTION.SIMPLE` | 67 | 75 | 50 | 48 | 201 |
| 49 | `DS.SORT.BASIC` | `DS.SORT.MERGE` | 67 | 77 | 50 | 49 | 201 |
| 50 | `DS.SORT.SWAP.BUBBLE` | `DS.SORT.SWAP.QUICK` | 72 | 73 | 50 | 50 | 201 |

## 6. strength 分布

| strength | 条数 | 语义 |
|---|---|---|
| 90 | 9 | 硬前置（未满足则不进「新知」推荐） |
| 80 | 19 | 硬前置（未满足则不进「新知」推荐） |
| 50 | 22 | 软前置（仅学习顺序建议） |
| **合计** | **50** | 硬 28 / 软 22 |

## 7. 环检测结果

| 项 | 结果 |
|---|---|
| 重复边 | 0 ✅ |
| 自环 | 0 ✅ |
| 有向环（Kahn 拓扑） | **无环 ✅** |
| 两端 node_type | 全 concept，0 container ✅ |
| source | 全 `manual` ✅ |
| note 前缀 | 50/50 含「M5 前置关系种子」✅ |

## 8. 推荐变化前后对比

**写入前**（`GET /recommendations/today?limit=10`）：
- 全部 **10 条** `learn_new`、`score=84.5`、`unlock=1.0` → **完全同分**

**写入后**：
| 排名 | 知识点 | score | unlock | gap | goal | urgency | recency |
|---|---|---|---|---|---|---|---|
| 1 | 线性表的定义与基本操作（kp=9） | **135.2** | 1.6 | 1.3 | 1.25 | 1.0 | 1.0 |
| 2 | 树的基本概念与术语（kp=32） | **135.2** | 1.6 | 1.3 | 1.25 | 1.0 | 1.0 |
| 3 | 图的基本概念与术语（kp=45） | **135.2** | 1.6 | 1.3 | 1.25 | 1.0 | 1.0 |
| 4 | 排序的基本概念与稳定性（kp=67） | **135.2** | 1.6 | 1.3 | 1.25 | 1.0 | 1.0 |
| 5 | 算法的定义与特性（kp=4） | **125.06** | 1.48 | 1.3 | 1.25 | 1.0 | 1.0 |
| 6 | 时间复杂度分析（kp=6） | **104.78** | 1.24 | 1.3 | 1.25 | 1.0 | 1.0 |
| 7 | 串的定义与存储结构（kp=28） | **104.78** | 1.24 | 1.3 | 1.25 | 1.0 | 1.0 |
| 8 | 查找的基本概念与平均查找长度（kp=60） | **104.78** | 1.24 | 1.3 | 1.25 | 1.0 | 1.0 |
| 9 | 数据结构基本概念（kp=2） | **94.64** | 1.12 | 1.3 | 1.25 | 1.0 | 1.0 |
| 10 | 直接插入排序（kp=69） | **94.64** | 1.12 | 1.3 | 1.25 | 1.0 | 1.0 |

**量化对比**：
| 指标 | 写入前 | 写入后 |
|---|---|---|
| 不同 score 档数 | 1（`{84.5: 10}`） | **4**（`{135.2: 4, 125.06: 1, 104.78: 3, 94.64: 2}`） |
| unlock 因子取值 | 1 档 `[1.0]` | **4 档** `[1.6, 1.48, 1.24, 1.12]`（全池 5 档，`1.0` 档排名在 10 名之后） |
| 可见候选是否全部落于硬前置阻塞集 | — | 否，前 10 全部为**未阻塞**节点 ✅ |

**结论**：`unlock` 因子已生效 → 推荐由「单一分数」变为「**分层排序**」，同分问题**显著缓解**。

### 8.1 学习路径验证（`GET /knowledge-points/64/path`）

目标：**平衡二叉树（AVL树）**，ready=False，threshold=70，steps=4

| step | 知识点 | node_type | mastery | satisfied | is_target |
|---|---|---|---|---|---|
| 1 | 树的基本概念与术语 | concept | None | False | False |
| 2 | 二叉树的定义与性质 | concept | None | False | False |
| 3 | 二叉排序树 | concept | None | False | False |
| 4 | 平衡二叉树（AVL树） | concept | None | False | True |

路径已出现真实前置链（树概念 → 二叉树 → BST → AVL），且前置未满足时 `satisfied=False / ready=False` ✅

### 8.2 mastery 不变验证

`GET /mastery/summary` 写入前后**逐字段一致**：`{"total":0,"weak_count":0,"average_score":0.0,"today_review_count":2,"weak_threshold":60}` ✅

## 9. 回滚方案

**方式 A（推荐 · 走 API，可逐条/可全量）**：
```
DELETE /api/v1/knowledge-points/{target_id}/prerequisites/{prerequisite_id}
```
逐条删除下表 50 组 `(target_id, source_id)` 即可；该表**无外键被其他表引用**，删除不影响题目 / 掌握度 / 错题 / 答题记录。

**方式 B（SQL 兜底 · 需另行批准）**：
```sql
DELETE FROM knowledge_point_prerequisites WHERE note LIKE 'M5 前置关系种子%';
```
`note` 前缀 `M5 前置关系种子` 即本次写入的回滚抓手，仅命中本次 50 条。

**回滚影响**：推荐 `unlock` 因子回到恒 1.0（重新同分）；学习路径回到单节点。无 schema 变化、无需 migration 回退。

**回滚映射表（50 组，target_id ← source_id / edge_id）**：
| edge_id | target_id | source_id |
|---|---|---|
| 1 | 3 | 2 |
| 2 | 11 | 9 |
| 3 | 13 | 9 |
| 4 | 19 | 9 |
| 5 | 25 | 9 |
| 6 | 14 | 13 |
| 7 | 15 | 13 |
| 8 | 21 | 19 |
| 9 | 22 | 19 |
| 10 | 23 | 19 |
| 11 | 26 | 25 |
| 12 | 29 | 28 |
| 13 | 34 | 32 |
| 14 | 35 | 34 |
| 15 | 36 | 34 |
| 16 | 38 | 34 |
| 17 | 63 | 34 |
| 18 | 37 | 36 |
| 19 | 39 | 38 |
| 20 | 46 | 45 |
| 21 | 48 | 46 |
| 22 | 49 | 46 |
| 23 | 55 | 46 |
| 24 | 57 | 48 |
| 25 | 58 | 57 |
| 26 | 64 | 63 |
| 27 | 6 | 4 |
| 28 | 7 | 4 |
| 29 | 16 | 11 |
| 30 | 62 | 11 |
| 31 | 16 | 13 |
| 32 | 41 | 32 |
| 33 | 42 | 36 |
| 34 | 43 | 36 |
| 35 | 52 | 46 |
| 36 | 53 | 46 |
| 37 | 56 | 46 |
| 38 | 65 | 60 |
| 39 | 30 | 29 |
| 40 | 76 | 38 |
| 41 | 70 | 69 |
| 42 | 30 | 6 |
| 43 | 78 | 6 |
| 44 | 61 | 11 |
| 45 | 62 | 60 |
| 46 | 69 | 67 |
| 47 | 72 | 67 |
| 48 | 75 | 67 |
| 49 | 77 | 67 |
| 50 | 73 | 72 |

## 10. 无污染核查（写入前后对比）

| 表 | 写入前 | 写入后 | 变化 |
|---|---|---|---|
| knowledge_points | 78 (56/22) | 78 (56/22) | 不变 ✅ |
| knowledge_point_prerequisites | 0 | **50** | 预期新增 ✅ |
| user_knowledge_point_mastery | 0 | 0 | 不变 ✅ |
| questions | 8 | 8 | 不变 ✅ |
| question_knowledge_points | 0 | 0 | 不变 ✅（D6 延后） |
| users | 1 | 1 | 不变 ✅ |
| knowledge_point_import_batches | 1 | 1 | 不变 ✅ |
| answer_records | 4 (wrong 2) | 4 (wrong 2) | 不变 ✅ |

## 11. 边界（未做事项）

- ❌ 未改代码、未改 migration、未 build、未 deploy、未 restart、未启动 worker/beat
- ❌ 未修改推荐算法与评分公式；未调整 mastery
- ❌ 未处理题目↔知识点关联（D6 延后）；未新增/修改任何后端 API
- ❌ 未进入 M6 / BKT / DeepKT / 自动生成题目
- ⚠️ 已知局限（非缺陷）：`UNLOCK_CAP=0.6` 使传递后置 ≥5 的章节根封顶 → **top-4（线性表/树/图/排序）仍同分 135.2**；如要彻底拉开需**边强度策略调整或算法改动**，本阶段不动。
