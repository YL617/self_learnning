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

在 `docker-compose.yml` 的 `backend.environment` 中配置：

```dotenv
DATABASE_URL=mysql+pymysql://ai_study:ai_study_pass@mysql:3306/ai_study?charset=utf8mb4
REDIS_URL=redis://redis:6379/0
DEEPSEEK_API_KEY=sk-xxx
SECRET_KEY=请替换为随机字符串
```

生产环境必须修改 `SECRET_KEY`，不要使用默认值。

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
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

## 7. 备份

```bash
docker compose exec mysql mysqldump -u root -p ai_study > backup.sql
```

## 8. 常见问题

- 后端无法访问外网时，AI 会自动降级为离线模板
- 首次构建较慢，建议保留 Docker 镜像缓存
- 内存不足时先关闭 worker 服务，仅保留 backend
