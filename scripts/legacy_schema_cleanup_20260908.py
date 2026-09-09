"""One-time cleanup CLI for the reviewed 20260908 legacy MySQL schema.

Default mode is read-only. Apply requires an explicit flag, a separately created
backup proof, and the fingerprint printed by a prior dry run. This tool never
stamps Alembic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base
from app.core.legacy_cleanup import (
    apply_cleanup,
    assess_snapshot,
    collect_cleanup_snapshot,
    scan_repository_index_dependencies,
)
from app.core.legacy_cleanup_manifest import (
    LEGACY_REVISION,
    TARGET_REVISION,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or apply the reviewed 20260908 legacy index cleanup."
    )
    parser.add_argument("--apply", action="store_true", help="execute reviewed DDL")
    parser.add_argument(
        "--backup-proof",
        type=Path,
        help="JSON evidence produced by the separate backup process",
    )
    parser.add_argument(
        "--plan-fingerprint",
        help="fingerprint printed by the latest dry run",
    )
    return parser


def _print_blocked(reasons: list[str]) -> None:
    print("CLEANUP BLOCKED")
    for reason in reasons:
        print(f"ERROR {reason}")


def _print_dry_run(assessment) -> None:
    print(assessment.status)
    print()
    print("Current revision:")
    print(LEGACY_REVISION)
    if assessment.status == "LEGACY CLEANUP REQUIRED":
        drops = [operation for operation in assessment.pending if operation.operation == "drop"]
        creates = [operation for operation in assessment.pending if operation.operation == "create"]
        print()
        print("DROP INDEX:")
        for number, operation in enumerate(drops, 1):
            print(f"{number}. {operation.table}.{operation.index}{operation.columns}")
        print()
        print("CREATE INDEX:")
        for number, operation in enumerate(creates, 1):
            print(f"{number}. {operation.table}.{operation.index}{operation.columns}")
        print()
        print("Target schema:")
        print(f"Equivalent to {TARGET_REVISION}")
        print()
        print(f"Plan fingerprint: {assessment.plan_fingerprint}")
    print()
    print("No changes were made.")
    print("External BI, manual SQL, and third-party index hints still require human confirmation.")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    findings = scan_repository_index_dependencies(ROOT)
    if findings:
        _print_blocked([f"runtime index dependency found at {finding}" for finding in findings])
        return 2
    if args.apply and (args.backup_proof is None or not args.plan_fingerprint):
        _print_blocked(["--apply requires --backup-proof and --plan-fingerprint"])
        return 2

    engine = create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
    try:
        if not args.apply:
            assessment = assess_snapshot(
                collect_cleanup_snapshot(engine, Base, check_busy=False)
            )
            if assessment.blockers:
                _print_blocked(assessment.blockers)
                print("No changes were made.")
                return assessment.exit_code
            _print_dry_run(assessment)
            return 0

        result = apply_cleanup(
            engine,
            Base,
            backup_proof=args.backup_proof,
            expected_fingerprint=args.plan_fingerprint,
        )
        print(result.status)
        for operation in result.completed:
            print(f"SUCCESS {operation}")
        if result.status == "CLEANUP BLOCKED":
            for blocker in result.blockers:
                print(f"ERROR {blocker}")
            if result.failure:
                print(f"ERROR failure_type={result.failure}")
            if result.recovery_sql:
                print("RECOVERY PLAN:")
                for sql in result.recovery_sql:
                    print(sql)
            return result.exit_code
        if result.status == "ALREADY CLEAN":
            print("No changes were made.")
            return 0
        print()
        print("Next required checks:")
        print("1. Drift Checker")
        print("2. Adoption Inspector")
        print()
        print(f"Do NOT stamp until inspector reports SAFE TO ADOPT TO {TARGET_REVISION}")
        return 0
    except Exception as exc:  # noqa: BLE001 -- CLI boundary suppresses SQL and credentials.
        _print_blocked([f"inspection failed ({type(exc).__name__}); details suppressed"])
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
