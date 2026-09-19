#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077
cd "${APP_DIR:-/opt/ai-study}"

checkout_status=$(git status --porcelain)
if [ -n "$checkout_status" ]; then
  if [ "$checkout_status" != ' M scripts/backup_mysql.sh' ] ||
     [ "$(git diff --numstat -- scripts/backup_mysql.sh)" != $'0\t0\tscripts/backup_mysql.sh' ]; then
    echo 'ERROR: unreviewed working tree changes; deployment stopped.'
    exit 1
  fi
fi
if [ "${1:-}" = '--check-checkout' ]; then exit 0; fi
commit=$(git rev-parse HEAD)
if [ -n "${EXPECTED_COMMIT:-}" ] && [ "$commit" != "$EXPECTED_COMMIT" ]; then
  echo 'ERROR: HEAD does not match EXPECTED_COMMIT.'
  exit 1
fi
echo "Deploy commit=$commit image=${BACKEND_IMAGE:-ai-study-backend:latest}"
log_dir="${DEPLOY_LOG_DIR:-/var/log/ai-study-deploy}/$(date -u +%Y%m%dT%H%M%S)-$$"
mkdir -p "$log_dir"

private_step() {
  local name="$1"
  shift
  if "$@" >"$log_dir/$name.log" 2>&1; then
    echo "$name: success"
  else
    echo "ERROR: $name failed; deployment stopped. Restricted log: $log_dir/$name.log"
    return 1
  fi
}

private_step config docker compose config --quiet
private_step storage-preflight python3 scripts/check_runtime_storage.py
background="${ENABLE_BACKGROUND:-auto}"
case "$background" in
  auto)
    active=$(docker compose --profile background ps --status running --services worker beat)
    if [ -n "$active" ]; then background=1; else background=0; fi ;;
  0|1) ;;
  *) echo 'ERROR: ENABLE_BACKGROUND must be auto, 0, or 1'; exit 1 ;;
esac

private_step build docker compose build backend web
private_step database-ready docker compose up -d --wait --wait-timeout 120 mysql redis
private_step revision-before docker compose run --rm --no-deps -T backend alembic current
private_step backup bash "${BACKUP_SCRIPT:-scripts/backup_mysql.sh}"

# Quiesce old processes for the maintenance window before changing schema.
private_step stop-background docker compose --profile background stop worker beat
private_step stop-backend docker compose stop backend
private_step storage-final python3 scripts/check_runtime_storage.py
private_step migration docker compose run --rm --no-deps -T backend alembic upgrade head
private_step revision-ready docker compose run --rm --no-deps -T backend python -m app.core.revision_guard
private_step drift-ready docker compose run --rm --no-deps -T backend python -m app.core.schema_drift

private_step backend-start docker compose up -d --no-deps --no-build --wait --wait-timeout 120 backend
if [ "$background" = 1 ]; then
  private_step worker-start docker compose --profile background up -d --no-deps --no-build worker
  private_step beat-start docker compose --profile background up -d --no-deps --no-build beat
  private_step worker-health docker compose --profile background exec -T worker \
    celery -A app.tasks.celery_app inspect ping --timeout=10
  private_step beat-revision docker compose --profile background exec -T beat python -m app.core.revision_guard
fi
private_step web-start docker compose up -d --no-deps --no-build web
private_step health docker compose exec -T backend python -c \
  "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status == 200"
private_step web-health docker compose exec -T web wget -q -O /dev/null http://127.0.0.1/
private_step revision-after docker compose exec -T backend python -m app.core.revision_guard
private_step drift-after docker compose exec -T backend python -m app.core.schema_drift
echo "Deployment complete: commit=$commit. Revision and drift results: $log_dir"
