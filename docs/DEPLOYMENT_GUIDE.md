# AI智学管家 部署指南

## 0. 本机生产参数

| 项目 | 值 |
| --- | --- |
| 域名 | yl617.xyz |
| 服务器 IP | 8.136.194.163 |
| 服务器系统 | Rocky Linux 9.2 64 位 |
| ICP 备案号 | 皖ICP备2026025771号 |
| 管理员邮箱 | 3524045145@qq.com |

## 1. 环境要求

- Docker 与 Docker Compose
- 2 核 4G 云服务器（Ubuntu 22.04 或更高）
- 可选：域名与 HTTPS 证书

## 1.1 Rocky Linux 初始化

```bash
# 更新系统
sudo dnf update -y

# 安装 Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# 开放端口（80/443 给 Nginx，8000 仅内网或按需开放）
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

验证：

```bash
docker --version
docker compose version
```

## 1.2 一键部署脚本

脚本会完成：安装 Docker、开放端口、拉取代码、生成 `.env`、构建 Web/后端镜像、启动服务并执行迁移。

```bash
sudo dnf install -y git
git clone https://github.com/YL617/self_learnning.git /tmp/ai-study-deploy
sudo bash /tmp/ai-study-deploy/scripts/deploy_production.sh
```

执行后编辑 `/opt/ai-study/.env`，至少填写 `SECRET_KEY` 与 `DEEPSEEK_API_KEY`，然后重启：

```bash
cd /opt/ai-study
docker compose up -d
```

## 1.3 拉取并启动项目（手动方式）

```bash
cd /opt
git clone https://github.com/YL617/self_learnning.git ai-study
cd ai-study
cp .env.example backend/.env
```

编辑 `backend/.env` 与根目录 `.env`，至少配置：

```dotenv
SECRET_KEY=替换为随机长字符串
CORS_ORIGINS=https://yl617.xyz
DEEPSEEK_API_KEY=替换为你的 DeepSeek Key
ADMIN_INITIAL_EMAIL=3524045145@qq.com
DATABASE_URL=mysql+pymysql://ai_study:ai_study_pass@mysql:3306/ai_study?charset=utf8mb4
```

然后启动：

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

## 2. 一键启动

```bash
docker compose up -d --build
```

默认服务：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| mysql | 3306 | 业务数据库 |
| redis | 6379 | 缓存与 Celery |
| web | 5173 | Vue3 构建产物 + Nginx |
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
    server_name yl617.xyz;

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

签发 HTTPS：

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yl617.xyz
```

`web` 服务已使用 Docker 内 Nginx 托管构建产物，外层 Nginx 只需把 `location /` 代理到 `http://127.0.0.1:5173`。

## 3.2 上线检查清单

- [ ] 域名 yl617.xyz 已解析到 8.136.194.163
- [ ] HTTPS 证书生效
- [ ] `.env` 已配置 `SECRET_KEY`、`CORS_ORIGINS=https://yl617.xyz`、`DEEPSEEK_API_KEY`、`ADMIN_INITIAL_EMAIL=3524045145@qq.com`
- [ ] 首次启动后执行 `alembic upgrade head`
- [ ] 管理员账号可通过 `ADMIN_INITIAL_EMAIL` 初始化
- [ ] 后台可生成激活码，用户可兑换会员
- [ ] DeepSeek 余额与用量可在 `/admin` 查看
- [ ] 页面底部展示 ICP 备案号 皖ICP备2026025771号

## 7. 备份

```bash
docker compose exec mysql mysqldump -u root -p ai_study > backup.sql
```

## 8. 常见问题

- 后端无法访问外网时，AI 接口会返回 502，不会生成模板内容
- 首次构建较慢，建议保留 Docker 镜像缓存
- 内存不足时先关闭 worker 服务，仅保留 backend
