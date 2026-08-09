# AI智学管家整合开发计划：AI 监控 + 个人中心 + 管理系统

> 版本 V1.0，日期 2026-08-10

## 1. 目标

在 V9.0 架构内补齐管理员身份体系、用户个人中心、DeepSeek 余额与用量监控、独立 `/admin` 管理后台，为后续运营和内容治理提供基础。

## 2. 已确认决策

- 个人中心：新增 `/profile`，入口放右上角头像区，不放侧边栏；账号设置保留导出/注销
- 账号能力：头像上传、昵称修改、密码修改、学情资料展示
- 学习数据：专注、计划、练习、错题、周报入口
- 会员：仅展示，不接支付，由管理员后台调整
- 小程序：仅同步昵称、头像、会员等级
- 管理系统：独立 `/admin` 后台，`users.role` 角色模型，`ADMIN_INITIAL_EMAIL` 初始化
- 内容管理：题目/文档可查看删除，课程完整 CRUD
- AI 监控：仅 DeepSeek，管理员可见，Celery 每小时刷新 + 手动刷新

## 3. 数据模型

| 表 | 变更 |
| --- | --- |
| users | 新增 nickname、avatar_path、role |
| ai_provider_snapshots | 新增，保存 DeepSeek 余额快照 |
| ai_usage_records | 新增，按日保存 Token 与费用 |

## 4. 接口清单

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| PATCH | /users/me | 登录用户 | 修改昵称 |
| POST | /users/me/password | 登录用户 | 修改密码 |
| POST | /users/me/avatar | 登录用户 | 上传头像 |
| GET | /admin/users | 管理员 | 用户列表 |
| PATCH | /admin/users/{id} | 管理员 | 禁用/会员/角色 |
| GET | /admin/ai-monitor | 管理员 | AI 余额与用量 |
| POST | /admin/ai-monitor/refresh | 管理员 | 刷新监控，60 秒冷却 |
| GET | /admin/stats/overview | 管理员 | 运营看板 |
| GET | /admin/questions | 管理员 | 题目列表 |
| DELETE | /admin/questions/{id} | 管理员 | 删除题目 |
| GET | /admin/documents | 管理员 | 文档列表 |
| DELETE | /admin/documents/{id} | 管理员 | 删除文档 |
| GET/POST/PATCH/DELETE | /admin/courses | 管理员 | 课程管理 |

## 5. 实现要点

- 管理员权限统一走 `get_current_admin`，前端 `/admin` 路由守卫
- DeepSeek 余额查询使用 `GET https://api.deepseek.com/user/balance`，用量依次尝试 `usage/cost`、`usage/amount`
- 低余额阈值默认 ¥10，可在 `AI_LOW_BALANCE_THRESHOLD` 配置
- 通义千问、智谱 GLM 暂不支持官方余额查询，界面明确标注不可用
- 所有管理接口不暴露 API Key

## 6. 测试与验收

- 后端 pytest 46 项通过，ruff 通过
- Web 构建与 Vitest 8 项通过，小程序类型检查通过
- 无头浏览器验证 `/profile` 与 `/admin` 正常渲染
- DeepSeek 真实余额联调通过
