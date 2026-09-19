#!/usr/bin/env bash
set +x
set -euo pipefail
APP_DIR="${APP_DIR:-/opt/ai-study}"
cd "$APP_DIR"
bash scripts/production_release.sh --check-checkout
git pull --ff-only
# Load the release implementation from the newly selected commit.
exec bash scripts/production_release.sh
