import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def bash_path():
    bash = shutil.which("bash")
    if bash:
        return bash
    git = shutil.which("git")
    candidate = Path(git).resolve().parents[1] / "bin/bash.exe" if git else Path("missing")
    if candidate.is_file():
        return str(candidate)
    pytest.skip("Bash unavailable; CI runs these orchestration tests on Linux")


def executable(path, content):
    path.write_text("#!/usr/bin/env bash\n" + content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture()
def release_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("production_release.sh", "update_production.sh", "deploy_production.sh"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    (tmp_path / ".env").touch()
    executable(bin_dir / "git", '''
case "$*" in
  'status --porcelain') printf '%s' "${DIRTY:-}" ;;
  'rev-parse HEAD') echo test-reviewed-commit ;;
  'pull --ff-only') exit "${PULL_FAILURE:-0}" ;;
  'diff --numstat -- scripts/backup_mysql.sh') printf '0\\t0\\tscripts/backup_mysql.sh' ;;
esac
''')
    executable(bin_dir / "docker", '''
echo "$*" >> "$TRACE"
case "$*" in
  *'ps --status running --services worker beat'*) printf '%s' "${ACTIVE_BACKGROUND:-}" ;;
esac
if [ -n "${FAIL_MATCH:-}" ] && [[ "$*" == *"$FAIL_MATCH"* ]]; then
  echo 'mysql://user:must-not-print@db' >&2
  exit 7
fi
''')
    executable(bin_dir / "python3", 'echo storage-check >> "$TRACE"\nexit "${STORAGE_FAILURE:-0}"\n')
    executable(scripts / "backup_mysql.sh", 'echo BACKUP >> "$TRACE"\nexit "${BACKUP_FAILURE:-0}"\n')
    return {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "APP_DIR": tmp_path.as_posix(), "TRACE": (tmp_path / "trace.txt").as_posix(),
        "DEPLOY_LOG_DIR": (tmp_path / "logs").as_posix(), "ENABLE_BACKGROUND": "1",
        "TEST_BIN": bin_dir.as_posix(),
        "FAIL_MATCH": "", "EXPECTED_COMMIT": "",
    }


def run_release(env, script="production_release.sh"):
    launcher = ('bin="$TEST_BIN"; if command -v cygpath >/dev/null; then bin=$(cygpath -u "$bin"); fi; '
                'export PATH="$bin:$PATH"; exec bash "$1"')
    result = subprocess.run([bash_path(), "-c", launcher, "release-test",
                             (Path(env["APP_DIR"]) / "scripts" / script).as_posix()],
                            env=env, capture_output=True, text=True, check=False)
    trace = Path(env["TRACE"])
    return result, trace.read_text() if trace.exists() else ""


@pytest.mark.parametrize("failure", ["alembic current", "alembic upgrade head",
                                     "app.core.revision_guard", "app.core.schema_drift"])
def test_release_failure_never_starts_new_application(release_env, failure):
    result, trace = run_release({**release_env, "FAIL_MATCH": failure})
    assert result.returncode != 0
    assert failure in trace
    assert "up -d --no-deps --no-build" not in trace
    assert "must-not-print" not in result.stdout + result.stderr


def test_backup_failure_stops_before_migration(release_env):
    result, trace = run_release({**release_env, "BACKUP_FAILURE": "1"})
    assert result.returncode != 0
    assert "BACKUP" in trace
    assert "alembic upgrade" not in trace
    assert "stop backend" not in trace


def test_successful_release_order(release_env):
    result, trace = run_release(release_env)
    assert result.returncode == 0, result.stderr + result.stdout
    steps = ["build backend web", "mysql redis", "alembic current", "BACKUP", "stop worker beat",
             "stop backend", "alembic upgrade head", "app.core.revision_guard",
             "app.core.schema_drift", "--wait-timeout 120 backend", "--no-build worker", "--no-build beat"]
    positions = [trace.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "stamp" not in trace and "downgrade" not in trace


@pytest.mark.parametrize("active,enabled", [("", False), ("worker\nbeat", True)])
def test_background_auto_preserves_enabled_state(release_env, active, enabled):
    result, trace = run_release({**release_env, "ENABLE_BACKGROUND": "auto", "ACTIVE_BACKGROUND": active})
    assert result.returncode == 0
    assert ("--no-build worker" in trace) == enabled


@pytest.mark.parametrize("script", ["update_production.sh", "deploy_production.sh"])
def test_pull_failure_never_deploys(release_env, script):
    result, trace = run_release({**release_env, "PULL_FAILURE": "1"}, script)
    assert result.returncode != 0
    assert "build backend" not in trace


def test_unreviewed_files_block_deployment(release_env):
    result, trace = run_release({**release_env, "DIRTY": "?? unreviewed.py"})
    assert result.returncode != 0
    assert not trace


def test_backup_mode_only_change_is_preserved(release_env):
    result, _ = run_release({**release_env, "DIRTY": " M scripts/backup_mysql.sh"})
    assert result.returncode == 0


def test_unmounted_storage_blocks_before_build(release_env):
    result, trace = run_release({**release_env, "STORAGE_FAILURE": "1"})
    assert result.returncode != 0
    assert "build backend" not in trace


def test_shell_syntax():
    for name in ("production_release.sh", "deploy_production.sh", "update_production.sh"):
        subprocess.run([bash_path(), "-n", str(ROOT / "scripts" / name)], check=True)


def test_storage_mount_must_cover_actual_directory():
    spec = importlib.util.spec_from_file_location("storage", ROOT / "scripts/check_runtime_storage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.covered("/app/uploads", [{"Type": "volume", "Destination": "/app/uploads"}])
    assert not module.covered("/app/uploads", [{"Type": "volume", "Destination": "/app/uploads-old"}])
    assert not module.covered("/app/uploads", [{"Type": "tmpfs", "Destination": "/app/uploads"}])
