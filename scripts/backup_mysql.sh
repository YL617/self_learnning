#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/opt/ai-study/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

mkdir -p /backup
cd /opt/ai-study
docker compose exec -T mysql mysqldump \
  --no-tablespaces \
  -u"${MYSQL_USER:-ai_study}" \
  -p"${MYSQL_PASSWORD:-ai_study_pass}" \
  "${MYSQL_DATABASE:-ai_study}" \
  > "/backup/ai_study_$(date +%F).sql"

find /backup -name "ai_study_*.sql" -mtime +14 -delete
