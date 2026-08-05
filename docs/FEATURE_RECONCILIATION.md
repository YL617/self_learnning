# V8.0 → V9.0 功能合并清单

> 目的：将《AI智学管家项目开发目标文档V8.0》中更全面的功能设计吸收进本项目。
> 原则：**V9.0 的技术架构为唯一基准**；V8.0 仅作为功能与产品设计参考。凡涉及框架、技术栈、部署架构的选择，一律以 V9.0 为准，不得产生冲突。

## 1. 合并结论

- V9.0 保留：Vue3 + TypeScript Web 端、Uni-app 微信小程序、FastAPI、MySQL、Redis、Celery、AI Gateway（DeepSeek/通义/GLM）、RAG（LlamaIndex + Chroma/Milvus）、Docker 部署。
- V8.0 采纳：学情画像与冷启动、动态计划调整、知识标签与热力图、四重出题质检、艾宾浩斯复习调度、待办与日历、主动提醒推送、完整宠物经济与防作弊/防沉迷、交互式文档出题菜单、代码沙箱细节、文件上传防御、商业化与合规目标、性能指标。
- V8.0 不采纳（框架冲突）：桌面端 Tauri/Electron、移动端 Flutter、多租户 Tenant ID 架构、K8s 沙箱编排、LangChain 绑定、DeepSeek 单模型绑定。

## 2. 功能合并清单

### 2.1 学情画像与冷启动

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 结构化表单 + AI 对话录入学情 | 采纳 | `user_profiles` 扩展；Web 资料页与小程序“我的”页支持录入 |
| 1 分钟破冰问卷（专业/年级/痛点/时间/目标/偏好） | 采纳 | 注册后引导流程，M1 完成 |
| 专家模板 + AI 微调生成破冰周计划 | 采纳 | 复用现有 `/plans/generate` 与专家模板兜底 |
| 能力基线自适应摸底测试 | 延后 | 作为 M3 后增强，不阻塞 MVP |
| 持续画像构建 | 采纳 | 行为数据（答题、专注、计划完成）回流到画像 |

### 2.2 智能学习规划

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 知识图谱自动生成路径 | 采纳（轻量版） | 用“学科 → 章节 → 知识点 → 标签”四级标签体系，不引入图数据库 |
| 难度梯度（最近发展区） | 采纳 | 出题与计划 Prompt 增加难度字段 |
| 精力匹配与时段安排 | 采纳 | `plan_items` 增加时间段建议与 `buffer_minutes` |
| 弹性缓冲 20% Buffer | 采纳 | 计划生成时按周任务量计算 Buffer |
| 滞后处理 / 超前奖励 / 行为追踪 | 采纳 | 新增 `plan_adjustment_logs`，AI 根据完成率动态调整 |
| 公开课程聚合 | 采纳 | 新增 `courses / course_chapters / course_knowledge_mapping`，仅做索引与外链跳转 |
| 课程大纲作为出题教材 | 采纳 | RAG 上下文增加课程大纲来源 |

### 2.3 智能测评与错题本

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| AI 动态习题生成（番茄钟/视频后触发） | 采纳 | `questions` 增加 `trigger_source`；专注完成后提示生成练习 |
| 四重质检闭环（RAG 约束 / AI 自检 / 格式规则 / 用户反馈） | 采纳 | `question_generator` 增加自检与格式校验；`questions` 增加质检字段 |
| 教育测量学指标（难度/区分度/干扰项） | 采纳（简化版） | `questions` 增加 `correct_rate`、`discrimination` 等统计字段 |
| 自动收录错题 | 采纳 | 现有 `answer_records → wrong_book_items` 链路已覆盖 |
| 艾宾浩斯复习调度（1/3/7/15/30 天） | 采纳 | `wrong_book_items` 增加 `next_review_date`、`review_stage` |
| AI 举一反三 | 采纳 | 现有“举一反三”接口强化 |
| 错题消灭奖励 +5 币 | 采纳 | 与 V9.0 现有 +5 币保持一致 |
| 题目反馈与人工复核 | 采纳 | 新增 `question_feedback` 表 |

### 2.4 个人效能与专注管理

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 待办事项 To-Do | 采纳 | 扩展 `plan_items` 或独立 `todos` 表 |
| 可视化日历（日/周/月 + 拖拽） | 采纳 | Web 端新增日历视图，M5/M6 |
| 沉浸式番茄钟 + 白噪音 | 采纳 | `focus_sessions` 增加音频设置；白噪音资源后置 |
| 防作弊（交互活跃度检测） | 采纳 | Web 端检测鼠标/键盘；小程序端检测页面切后台 |
| 专注统计与周报/月报 | 采纳 | `daily_stats` 聚合，图表在 M6 完成 |
| 每日提醒 | 采纳 | Celery Beat + 推送网关 |

### 2.5 智能监督与主动提醒

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 自定义定时检查点 | 采纳 | 新增 `reminders` 表 |
| 状态联动检查（任务未完成触发提醒） | 采纳 | Celery Beat 定时扫描 + 通知队列 |
| 多渠道推送（微信订阅/短信/邮件） | 采纳 | 先做站内提醒 + 邮件，微信订阅消息后置 |
| 全自动运行 | 采纳 | Celery Beat 调度，无需人工干预 |

### 2.6 宠物养成与激励系统

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 智学币完整经济（任务 +10 / 番茄钟 +5 / Combo +50/+200 / 错题消灭 +5） | 采纳 | `coin_transactions` 增加奖励类型；新增连续打卡字段 |
| 宠物饱食度 / 心情 / 经验 | 采纳 | `pets` 增加 `hunger`、`runaway`、`evolution_stage` |
| 进化路线与状态联动 | 采纳 | 按等级解锁外观，先做等级/经验 |
| 消耗体系（饲料 / 营养膏 / 请假条 / 寻回卷轴） | 采纳 | `shop_items` 与宠物接口扩展 |
| 每日收益上限（番茄钟最多 40 币） | 采纳 | 后端每日统计校验 |
| 连续专注 2 小时休息提醒 | 采纳 | 前端提示 + 宠物气泡 |
| 深夜饱食度消耗翻倍 | 采纳 | 后端按时段计算 |
| 社交海报分享 | 采纳 | 生成分享海报接口，M6 |

### 2.7 交互式文档出题引擎

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 多格式解析（PDF/Word/PPT/TXT/OCR） | 采纳 | 现有 `document_parser`；OCR 第二阶段 |
| AI 智能预分析 + 交互式菜单 | 采纳 | 新增 `POST /files/{id}/analyze`，返回结构化题型建议 |
| 按需定制题型数量 | 采纳 | 现有 `POST /files/{id}/questions` 扩展 |
| 联网搜索补全 | 延后 | 需接入搜索 API，作为 M6 后增强 |
| 文件完整性检测 | 采纳 | `document_parser` 返回完整性评估 |
| 适用场景扩展 | 采纳 | 文档与知识点标签通用化 |

### 2.8 代码沙箱（扩展功能）

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 在线编译 + 自动判分 | 采纳 | 新增 `submissions / test_cases / code_run_results` |
| 成熟沙箱服务（E2B / Piston） | 采纳 | 优先接入成熟 API，不引入 K8s |
| 支持 Python / C++ / Java | 采纳 | 按沙箱服务能力配置 |
| 正常/边界/异常测试用例 + 部分得分 | 采纳 | AI 出题时生成测试用例 |
| 超时 / 熔断 / 审计 | 采纳 | 沙箱适配层统一封装 |

### 2.9 文件上传防御

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 临时存储与生命周期清理 | 采纳 | `documents` 增加 `temp_cleanup_at`，Celery 定时清理 |
| 容量/页数/次数限制 | 采纳 | 文件接口增加配额校验 |
| 格式白名单 | 采纳 | 现有白名单保持 |
| 内容安全审核 | 采纳 | 上传后调用内容安全服务（可后置） |
| 频率限制 | 采纳 | API 层限流 |

### 2.10 商业化与运营目标

| V8.0 功能 | 处理方式 | V9.0 框架内落地 |
| --- | --- | --- |
| 免费 / Pro / 终身计费 | 延后 | 作为商业模式设计，不影响 MVP |
| B 端高校学习数据看板 | 延后 | M6 后可扩展管理后台 |
| 广告位与引流接口 | 延后 | 不做进比赛演示 |
| 数据加密、导出、账号注销 | 采纳 | 数据合规要求写入验收标准 |
| 敏感词过滤 | 采纳 | AI 输出后置过滤 |
| 垂直语料库沉淀 | 采纳 | 错题/反馈数据作为资产 |

## 3. 框架冲突项（以 V9.0 为唯一基准）

| V8.0 设计 | 冲突说明 | V9.0 处理 |
| --- | --- | --- |
| Tauri / Electron 桌面端 | 与 Web 端技术栈冲突 | 使用 Vue3 + TypeScript Web 端 |
| Flutter 移动端 | 与小程序技术栈冲突 | 使用 Uni-app 微信小程序 |
| 多租户 Tenant ID 架构 | 与轻量化应用架构冲突 | 当前按 `user_id` 逻辑隔离；多租户仅作为未来扩展说明 |
| K8s 沙箱编排 | 部署复杂度超出 V9.0 | 接入 E2B / Piston 等成熟沙箱服务 |
| LangChain | RAG 框架绑定冲突 | 使用 V9.0 的 LlamaIndex + 薄封装（或 Chroma 直接检索） |
| DeepSeek 单模型 | 与多模型网关冲突 | DeepSeek 为默认模型，通义千问 / GLM 作为备用 |

## 4. 数据模型增量（按里程碑落地）

| 阶段 | 新增/扩展 |
| --- | --- |
| M1 | `user_profiles` 增加破冰问卷字段：`school_level`、`gpa_rank`、`pain_point`、`available_minutes`、`learning_style`、`onboarding_completed` |
| M2 | `plan_items` 增加 `buffer_minutes`、`suggested_time_slot`；新增 `plan_adjustment_logs` |
| M3 | `questions` 增加 `difficulty`、`quality_status`、`correct_rate`、`discrimination`；新增 `question_feedback`、`knowledge_tags`、`question_tag_links` |
| M3 | `wrong_book_items` 增加 `review_stage`、`next_review_date`、`last_reviewed_at` |
| M4 | `documents` 增加 `temp_cleanup_at`、`quota_used`、`content_check_status`；新增 `file_analyze_results` |
| M5 | `pets` 增加 `hunger`、`runaway`、`evolution_stage`、`last_fed_at`；`coin_transactions` 增加 `reward_type`；新增 `checkin_records`、`shop_items` |
| M6 | 新增 `courses`、`course_chapters`、`course_knowledge_mapping`、`reminders`、`push_channels`、`submissions`、`test_cases`、`code_run_results` |

## 5. API 增量

- `POST /onboarding`：提交破冰问卷并生成第一份计划
- `POST /plans/{id}/adjust`：AI 动态调整计划
- `GET /knowledge-map`：个人知识掌握热力图
- `POST /questions/{id}/feedback`：题目纠错反馈
- `GET /wrong-book/review`：今日待复习错题
- `POST /files/{id}/analyze`：AI 预分析并返回题型菜单
- `GET/POST /todos`、`GET /calendar`：待办与日历
- `GET/POST /reminders`：自定义提醒
- `POST /pets/{id}/poster`：生成分享海报
- `POST /submissions`：代码提交与判分

## 6. 里程碑调整摘要

| 里程碑 | 调整内容 |
| --- | --- |
| M1 用户系统 | 增加 1 分钟破冰问卷与画像字段 |
| M2 AI 规划 | 增加难度梯度、Buffer、动态调整日志 |
| M3 出题与错题 | 增加四重质检、知识标签、艾宾浩斯复习调度 |
| M4 文件出题 + RAG | 增加交互式分析菜单、配额与生命周期清理 |
| M5 专注与宠物 | 增加完整智学币经济、防作弊/防沉迷、Combo |
| M6 演示 | 增加日历、提醒、课程聚合、周报/月报、分享海报 |

## 7. 实施优先级建议

1. **第一优先级（M1-M3 直接受益）**：破冰问卷、知识标签、四重质检、艾宾浩斯复习调度、错题反馈。
2. **第二优先级（M4-M5）**：交互式文档菜单、文件配额、宠物经济、Combo、防作弊/防沉迷。
3. **第三优先级（M6 及以后）**：日历与提醒、课程聚合、推送网关、代码沙箱、社交海报、管理看板。
