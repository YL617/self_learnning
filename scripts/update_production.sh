#!/usr/bin/env bash
set -euo pipefail

cd /opt/ai-study

echo "==> 1/4 拉取最新代码"
git pull --ff-only

echo "==> 2/4 构建前后端镜像"
docker compose build backend web

echo "==> 3/4 重启服务"
docker compose up -d --remove-orphans

echo "==> 4/4 执行数据库迁移"
docker compose exec -T backend alembic upgrade head

echo "更新完成：https://yl617.xyz"
