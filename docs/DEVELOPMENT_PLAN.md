# AI智学管家 开发计划（V9.0 落地版）

> 本文档将《AI智学管家项目开发目标文档V9.0_技术架构优化版》转化为可执行的开发计划，供团队按里程碑推进。
>
> **V8.0 功能合并说明**：V8.0 中更全面的功能设计已按“V9.0 框架为基准”原则吸收进本计划，逐项对照见 [FEATURE_RECONCILIATION.md](./FEATURE_RECONCILIATION.md)。

## 1. 项目目标与范围

**一句话目标**：面向高校学生，基于大模型与 RAG，提供「学习规划 - 知识学习 - 智能练习 - 错题反馈 - 行为激励」完整闭环的 AI 学习管理平台。

### MVP 演示主链路

注册登录 → AI 生成学习计划 → 按计划学习 → AI 出题练习 → 错题沉淀与举一反三 → 番茄钟专注 + 宠物成长激励。

### MVP 明确包含

- 用户注册、登录、个人资料（专业/年级/目标/每日学习时长）
- AI 学习规划（专家模板 + AI 调整）
- AI 智能出题（单选/填空/简答 + 自动解析 + AI 自检）
- 错题本与举一反三
- 文件智能出题（PDF / Word / PPT / TXT，图片 OCR 为第二阶段）
- 番茄钟、学习统计、智学币、AI 宠物
- Web 端（Vue3 + TS）+ 微信小程序端（Uni-app）+ FastAPI 后端

### MVP 明确不做（后续阶段）

- 复杂强化学习 / 多智能体编排
- 在线代码沙箱深度定制（第一阶段只接成熟沙箱）
- 多租户、高并发集群、数据分析平台
- 移动端原生 App（保持 Uni-app 多端编译能力即可）

## 2. 总体节奏（8 周，自 2026-08-06 起）

| 阶段 | 周期 | 主题 | 产出 |
| --- | --- | --- | --- |
| M0 骨架 | 第 1 周 | 基础设施与仓库骨架 | 可运行的前后端骨架、MySQL/Redis、CI 基础 |
| M1 用户 | 第 2 周 | 用户系统 + 冷启动 | 注册/登录/JWT/资料/权限中间件、1 分钟破冰问卷 |
| M2 规划 | 第 3-4 周 | AI 学习规划 | 模板规划 + AI 调整、难度梯度、Buffer、动态调整日志 |
| M3 练习 | 第 4-5 周 | AI 出题与错题 | 出题、四重质检、判题、知识标签、错题本、艾宾浩斯复习 |
| M4 文件 | 第 5-6 周 | 文件智能出题 + RAG | 文档解析、交互式题型菜单、切片、向量检索、配额与清理 |
| M5 激励 | 第 6-7 周 | 专注与宠物 | 番茄钟、统计、完整智学币经济、Combo、防作弊/防沉迷 |
| M6 演示 | 第 7-8 周 | 联调与打磨 | 日历/提醒/课程聚合、2核4G 云服务器部署、演示数据、答辩文档 |

## 3. 里程碑与验收标准

### M0：项目骨架可运行

- [ ] `docker compose up mysql redis` 可启动
- [ ] 后端 `/health` 可访问，SQLite/MySQL 均可初始化
- [ ] Web 端 `npm run dev` 可打开首页并代理 `/api`
- [ ] 小程序端可按官方模板启动 H5/微信小程序开发模式

### M1：用户系统

- [ ] 注册、登录、JWT 校验、当前用户信息
- [ ] 个人资料编辑
- [ ] 1 分钟破冰问卷（专业/年级/痛点/时间/目标/偏好）并生成第一份计划
- [ ] 错误提示与 401 统一处理

### M2：AI 学习规划

- [ ] 输入专业/年级/目标/时间后生成 4-12 周计划
- [ ] AI 服务不可用时接口返回明确错误提示（502），不再生成模板内容
- [ ] 难度梯度与精力匹配（高负荷任务安排到精力充沛时段）
- [ ] 每日任务预留约 20% Buffer
- [ ] 连续未完成任务时，AI 自动拆分或降低难度并记录调整原因
- [ ] 计划任务支持勾选完成，完成累计智学币与宠物经验

### M3：AI 出题与错题

- [ ] 按学科/知识点生成结构化题目
- [ ] 四重质检：RAG 约束、AI 自检、格式规则、用户反馈
- [ ] 题目带知识标签（学科 → 章节 → 知识点 → 标签）
- [ ] 判题、解析、错题入库
- [ ] 错题按 1/3/7/15/30 天进入复习调度
- [ ] 错题支持复习、掌握、举一反三
- [ ] 每道题支持“题目有误/答案错误”反馈

### M4：文件智能出题 + RAG

- [ ] PDF/Word/PPT/TXT 上传与解析
- [ ] AI 预分析文件并返回交互式题型菜单
- [ ] 文件配额、临时存储清理、内容安全校验
- [ ] 文本切片入库（Chroma）
- [ ] 基于检索上下文出题，降低幻觉
- [ ] 图片 OCR 与联网搜索补全（第二阶段）

### M5：专注与宠物

- [ ] 番茄钟开始/结束/统计
- [ ] 防作弊：挂机检测不计时；防沉迷：每日收益上限与连续专注提醒
- [ ] 智学币账本与完整经济（任务/专注/Combo/错题消灭）
- [ ] 宠物等级、经验、心情、饱食度、进化与喂食
- [ ] 连续打卡奖励（3 天 +50，7 天 +200，断签重置）

### M6：部署与演示

- [ ] 2 核 4G 服务器 Docker 部署
- [ ] 待办、可视化日历、每日提醒与站内通知
- [ ] 公开课程聚合页（B站/慕课/Coursera 索引 + 外链）
- [ ] 学习周报/月报与知识掌握热力图
- [ ] 演示账号与演示数据
- [ ] 答辩 PPT、架构图、视频录屏

## 4. 功能任务清单

### 4.1 用户系统

- 注册/登录接口、JWT 签发与鉴权中间件
- 用户资料表与资料编辑
- 前端登录页、注册页、路由守卫
- 小程序端登录接入

验收：登录态持久化，未登录访问受保护页面自动跳转登录。

### 4.2 AI 学习规划

- 专家模板库（按专业/年级/目标预置 3-5 套）
- AI 调整 Prompt 模板与 JSON 结构化输出
- 计划、计划项数据模型与 CRUD
- 计划完成状态流转（进行中 / 已完成）
- 破冰问卷与画像字段（`user_profiles`）
- 难度梯度、精力匹配、Buffer 与动态调整日志

验收：同输入重复生成结果稳定；AI 不可用时仍可生成计划。

### 4.3 AI 出题与错题管理

- 出题 Prompt（含知识点、题型、难度、解析、自检）
- 四重质检闭环（RAG 约束 / AI 自检 / 格式规则 / 用户反馈）
- 题目、作答记录、错题本数据模型
- 判题逻辑（单选精确匹配、简答关键词评分，AI 判题为第二阶段）
- 知识标签与个人知识热力图
- 艾宾浩斯复习调度（1/3/7/15/30 天）
- 举一反三：基于错题知识点重新出题

验收：题目包含题干/选项/答案/解析；错题可复习可掌握。

### 4.4 文件智能出题与 RAG

- 文档上传与格式识别（PDF/Word/PPT/TXT）
- 文本抽取、章节分析、切片
- AI 预分析并返回交互式题型菜单
- 文件配额、生命周期清理、内容安全校验
- Chroma 向量化与检索；LlamaIndex 流程封装
- 基于检索上下文出题
- 图片 OCR（第二阶段，可用百度/腾讯云 OCR 或本地 Tesseract）
- 联网搜索补全（第二阶段）

验收：上传一份 50 页以内 PDF 可解析并生成指定题型题目。

### 4.5 专注管理与宠物激励

- 番茄钟（25 分钟默认，可配置）
- 学习统计（今日/累计专注时长、答题数、正确率）
- 防作弊：交互活跃度检测，挂机不计时
- 防沉迷：每日番茄钟收益上限、连续专注 2 小时提醒、深夜消耗加倍
- 智学币流水（任务、专注、Combo、错题消灭、消费）
- 宠物成长（等级/经验/心情/饱食度/进化），喂食与道具消耗智学币

验收：完成一次番茄钟或答题可看到金币与经验变化。

### 4.6 编程学习辅助（扩展功能）

- 代码提交接口
- 接入成熟沙箱（E2B / Piston），不引入 K8s
- AI 生成正常/边界/异常测试用例，支持部分得分
- 超时、熔断、审计日志
- AI 错误分析

建议放在 M4 之后按时间余量决定，不作为演示必备项。

## 5. 数据模型规划

| 领域 | 表 | 关键字段 |
| --- | --- | --- |
| 用户 | users | email, username, hashed_password |
| 用户 | user_profiles | major, grade, goals, daily_study_minutes, weak_subjects |
| 规划 | study_plans | user_id, title, goal, start_date, end_date, status |
| 规划 | plan_items | plan_id, title, subject, scheduled_date, duration_minutes, completed |
| 练习 | questions | user_id, document_id, subject, knowledge_point, question_type, stem, options_json, answer, analysis |
| 练习 | answer_records | user_id, question_id, user_answer, is_correct, spent_seconds |
| 错题 | wrong_book_items | user_id, question_id, review_count, mastered |
| 知识库 | documents | user_id, filename, file_type, storage_path, status, chunks_count |
| 知识库 | knowledge_chunks | document_id, chunk_index, content, vector_id |
| 激励 | focus_sessions | user_id, task_label, started_at, ended_at, duration_minutes |
| 激励 | pets | user_id, name, level, exp, mood |
| 激励 | coin_transactions | user_id, amount, reason |
| 统计 | daily_stats | user_id, stat_date, focus_minutes, answered_count, correct_count, coin_earned |

## 6. API 规划（前缀 /api/v1）

| 模块 | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| 健康 | GET | /health | 服务状态 |
| 认证 | POST | /auth/register | 注册并返回 token |
| 认证 | POST | /auth/login | 登录 |
| 用户 | GET | /users/me | 当前用户 |
| 用户 | PATCH | /users/me/profile | 更新资料 |
| 规划 | GET | /plans | 我的计划 |
| 规划 | POST | /plans | 手动创建计划 |
| 规划 | POST | /plans/generate | AI 生成计划 |
| 规划 | GET | /plans/{id} | 计划详情 |
| 规划 | PATCH | /plans/items/{id} | 完成/更新计划项 |
| 练习 | POST | /questions/generate | AI 出题 |
| 练习 | GET | /questions | 题目列表 |
| 练习 | POST | /questions/{id}/answers | 提交作答 |
| 错题 | GET | /wrong-book | 错题本 |
| 错题 | PATCH | /wrong-book/{id} | 标记掌握/复习 |
| 文件 | POST | /files/upload | 上传文档 |
| 文件 | GET | /files | 我的文档 |
| 文件 | POST | /files/{id}/parse | 解析入库 |
| 文件 | POST | /files/{id}/questions | 基于文档出题 |
| 专注 | POST | /focus/sessions | 开始番茄钟 |
| 专注 | PATCH | /focus/sessions/{id}/complete | 结束番茄钟 |
| 专注 | GET | /focus/stats | 专注统计 |
| 激励 | GET | /pets | 我的宠物 |
| 激励 | PATCH | /pets/{id} | 改名 |
| 激励 | POST | /pets/{id}/feed | 喂食 |
| 激励 | GET | /coins/transactions | 智学币流水 |

## 7. AI 能力接入顺序

1. **Phase A（第 2-3 周）**：FastAPI 直接调用 DeepSeek OpenAI 兼容接口，先跑通「规划 + 出题」。
2. **Phase B（第 4 周）**：封装 AI Gateway（provider 注册、模型路由、降级、流式接口），接入通义千问 / GLM。
3. **Phase C（第 5 周起）**：接入 RAG（文档解析 → 切片 → Chroma → 检索增强出题）。

所有 AI 调用失败时应返回明确错误提示，不使用模板伪装结果。

## 8. 环境与部署

### 本地开发

```bash
# 基础设施（可选，后端默认 SQLite 可直接跑）
docker compose up -d mysql redis

# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Web 端
cd web
npm install
npm run dev

# 小程序端
cd mobile
pnpm install
pnpm dev:mp-weixin
```

### 比赛演示（2 核 4G）

- Docker Compose 部署：backend + worker + mysql + redis
- 前端构建后由 Nginx 托管，或演示时直接使用 Web 开发模式
- AI Key 通过环境变量注入，不写入代码库

## 9. 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| RAG 在低配服务器上耗时/占内存 | 演示卡顿 | 限制文档大小；切片 + 检索使用 Chroma；解析任务走 Celery 异步 |
| 大模型出题质量不稳定 | 演示翻车 | Prompt 结构化 + AI 自检 + 用户反馈；预置演示题库兜底 |
| API Key 费用/限流 | 演示中断 | 多模型切换 + 重试 + 缓存，失败时明确报错 |
| 双端并行开发量过大 | 延期 | Web 优先，小程序复用同一后端与页面结构 |
| 2 核 4G 资源不足 | 部署失败 | 演示环境去掉 Celery 高频任务；图片 OCR 放第二阶段 |

> 法律与合规风险、可行性风险完整清单见 [RISK_ASSESSMENT.md](./RISK_ASSESSMENT.md)。

## 10. 每周检查清单

- [ ] 本周目标是否上线可演示？
- [ ] 是否有 AI 调用失败路径未返回明确错误？
- [ ] 是否补充了后端测试与前端冒烟验证？
- [ ] 是否需要更新本文档的完成状态？
- [ ] 本周是否产出可用于比赛演示的截图/录屏素材？
