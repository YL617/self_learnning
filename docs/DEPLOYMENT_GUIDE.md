# AI智学管家 部署指南

## 1. 环境要求

- Docker 与 Docker Compose
- 2 核 4G 云服务器（Ubuntu 22.04 或更高）
- 可选：域名与 HTTPS 证书

## 2. 一键启动

```bash
docker compose up -d --build
```

默认服务：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| mysql | 3306 | 业务数据库 |
| redis | 6379 | 缓存与 Celery |
| backend | 8000 | FastAPI 后端 |
| worker | - | Celery Worker |

## 3. 配置

在项目根目录创建 `.env`，Docker Compose 会读取：

```dotenv
DATABASE_URL=mysql+pymysql://ai_study:ai_study_pass@mysql:3306/ai_study?charset=utf8mb4
REDIS_URL=redis://redis:6379/0
SECRET_KEY=请替换为随机字符串
CORS_ORIGINS=https://你的域名
DEEPSEEK_API_KEY=sk-xxx
ADMIN_INITIAL_EMAIL=管理员邮箱
TRIAL_DAYS=7
FREE_DAILY_AI_QUOTA=20
BASIC_DAILY_AI_QUOTA=60
ADVANCED_DAILY_AI_QUOTA=120
FULL_DAILY_AI_QUOTA=300
```

生产环境必须修改 `SECRET_KEY`，不要使用默认值；`CORS_ORIGINS` 必须包含你的正式域名。

## 3.1 域名、备案与 HTTPS

- 已完成的个人 ICP 备案，服务器需位于中国大陆并绑定备案域名
- 在域名服务商将 A 记录指向服务器公网 IP
- 使用 Certbot 为域名签发 HTTPS 证书，或使用云厂商托管证书
- Nginx 示例见下方，`server_name` 替换为你的正式域名

## 4. 数据库

首次启动自动建表。生产环境建议：

```bash
cd backend
alembic upgrade head
```

## 5. 演示数据

登录后访问 Web 首页，点击“填充演示数据”，或调用：

```bash
curl -X POST http://localhost:8000/api/v1/demo/seed \
  -H "Authorization: Bearer <token>"
```

## 6. Nginx 示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

若使用 Web 构建产物（`web/dist`）而非开发服务器，可将 `location /` 指向静态目录：

```nginx
location / {
    root /var/www/ai-study;
    try_files $uri $uri/ /index.html;
}
```

## 3.2 上线检查清单

- [ ] 域名已备案且解析到服务器
- [ ] HTTPS 证书生效
- [ ] `.env` 已配置 `SECRET_KEY`、`CORS_ORIGINS`、`DEEPSEEK_API_KEY`、`ADMIN_INITIAL_EMAIL`
- [ ] 首次启动后执行 `alembic upgrade head`
- [ ] 管理员账号可通过 `ADMIN_INITIAL_EMAIL` 初始化
- [ ] 后台可生成激活码，用户可兑换会员
- [ ] DeepSeek 余额与用量可在 `/admin` 查看

## 7. 备份

```bash
docker compose exec mysql mysqldump -u root -p ai_study > backup.sql
```

## 8. 常见问题

- 后端无法访问外网时，AI 接口会返回 502，不会生成模板内容
- 首次构建较慢，建议保留 Docker 镜像缓存
- 内存不足时先关闭 worker 服务，仅保留 backend
