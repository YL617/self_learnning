#!/usr/bin/env bash
set +x
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/ai-study}"
REPO_URL="https://github.com/YL617/self_learnning.git"

command -v git >/dev/null
command -v docker >/dev/null
command -v python3 >/dev/null
if [ ! -d "${APP_DIR}" ]; then
  git clone "${REPO_URL}" "${APP_DIR}"
fi
cd "${APP_DIR}"
if [ ! -f .env ]; then
  cp backend/.env.example .env
  chmod 600 .env
  echo 'Configure .env (database passwords, SECRET_KEY, CORS and AI credentials), then rerun.'
  exit 1
fi
bash scripts/production_release.sh --check-checkout
git pull --ff-only
exec bash scripts/production_release.sh
