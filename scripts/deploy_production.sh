#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-yl617.xyz}"
SERVER_IP="${SERVER_IP:-8.136.194.163}"
ADMIN_EMAIL="${ADMIN_EMAIL:-3524045145@qq.com}"
APP_DIR="${APP_DIR:-/opt/ai-study}"
REPO_URL="https://github.com/YL617/self_learnning.git"

echo "==> 1/6 安装 Docker（如已安装会跳过）"
if ! command -v docker >/dev/null 2>&1; then
  sudo dnf install -y dnf-plugins-core
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable --now docker
fi

echo "==> 2/6 开放 80/443 端口"
sudo firewall-cmd --permanent --add-service=http || true
sudo firewall-cmd --permanent --add-service=https || true
sudo firewall-cmd --reload || true

echo "==> 3/6 拉取代码到 ${APP_DIR}"
sudo mkdir -p /opt
if [ ! -d "${APP_DIR}" ]; then
  sudo git clone "${REPO_URL}" "${APP_DIR}"
fi
cd "${APP_DIR}"
sudo git pull --ff-only || true

echo "==> 4/6 生成生产配置 .env"
if [ ! -f .env ]; then
  sudo cp backend/.env.example .env
  sudo sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=https://${DOMAIN}|" .env
  sudo sed -i "s|^ADMIN_INITIAL_EMAIL=.*|ADMIN_INITIAL_EMAIL=${ADMIN_EMAIL}|" .env
  echo "    请编辑 ${APP_DIR}/.env，填写 SECRET_KEY 与 DEEPSEEK_API_KEY"
fi

echo "==> 5/6 启动 Docker 服务"
sudo docker compose up -d --build

echo "==> 6/6 执行数据库迁移"
sudo docker compose exec backend alembic upgrade head

echo "部署完成：后端健康检查 http://${SERVER_IP}:8000/health"
echo "Web 前端：http://${SERVER_IP}:5173"
echo "下一步：配置 Nginx 与 HTTPS，示例见 deploy/nginx-yl617.conf"
