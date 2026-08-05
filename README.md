# AI智学管家

基于大模型的自适应学习平台：学习规划 → 知识学习 → 智能练习 → 错题反馈 → 行为激励。

需求来源：[AI智学管家项目开发目标文档V9.0_技术架构优化版](./AI智学管家项目开发目标文档V9.0_技术架构优化版.docx)

## 仓库结构

```text
AI学习平台/
├── docs/                 # 开发计划、架构设计
├── backend/              # FastAPI 后端
├── web/                  # Vue3 + TypeScript Web 端
├── mobile/               # Uni-app 微信小程序端
└── docker-compose.yml    # MySQL / Redis / 后端编排
```

## 快速开始

### 1. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # 按需填写 AI API Key
uvicorn app.main:app --reload
```

默认使用 SQLite，零配置即可启动；需要 MySQL/Redis 时执行 `docker compose up -d mysql redis` 并修改 `backend/.env` 中的 `DATABASE_URL`。

也可一键启动完整后端栈（MySQL + Redis + FastAPI + Celery Worker）：

```bash
docker compose up -d --build
```

需要在 `docker-compose.yml` 的 `backend.environment` 中补充 `DEEPSEEK_API_KEY` / `QWEN_API_KEY` / `GLM_API_KEY` 后才能调用真实大模型。

### 2. 启动 Web 端

```bash
cd web
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`，接口已代理到 `http://localhost:8000`。

### 3. 启动小程序端

```bash
cd mobile
pnpm install
pnpm dev:mp-weixin
```

然后用微信开发者工具导入 `mobile/dist/dev/mp-weixin`。H5 调试可执行 `pnpm dev:h5`。

## AI 能力

在 `backend/.env` 中配置模型 Key：

```dotenv
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
QWEN_API_KEY=
GLM_API_KEY=
```

未配置 Key 时，规划与出题会自动降级为本地模板响应，保证演示不中断。

## 文档

- [开发计划](./docs/DEVELOPMENT_PLAN.md)
- [项目开发计划书](./docs/项目开发计划书.md)
- [技术架构](./docs/ARCHITECTURE.md)
- [V8.0 → V9.0 功能合并清单](./docs/FEATURE_RECONCILIATION.md)
- [法律风险与可行性检测报告](./docs/RISK_ASSESSMENT.md)
