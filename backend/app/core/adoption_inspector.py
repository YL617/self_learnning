"""Read-only, fail-closed schema adoption recommendations. No write mode."""

from dataclasses import dataclass, field
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.schema_drift import check_drift
from app.core.schema_profiles import load_profiles
from app.core.schema_reconciliation_manifest import reconciliation_manifest

TARGET = "20260909_001"
MIGRATION_DIR = Path(__file__).resolve().parents[2] / "alembic"


@dataclass
class AdoptionResult:
    status: str
    revision: str | None = None
    reasons: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def migration_chain(directory=MIGRATION_DIR):
    script = ScriptDirectory(str(directory))
    revisions = list(reversed(list(script.walk_revisions())))
    if script.get_heads() != [TARGET] or len(script.get_bases()) != 1:
        raise ValueError("Expected one base and the reviewed head")
    previous = None
    for revision in revisions:
        if (revision.down_revision != previous or revision.dependencies
                or revision.is_branch_point or revision.is_merge_point):
            raise ValueError("Migration graph is not a linear chain")
        previous = revision.revision
    return [r.revision for r in revisions]


def inspect_adoption(engine, base):
    info = [f"dialect={engine.dialect.name}"]
    revision = None

    def blocked(*reasons):
        return AdoptionResult("ADOPTION BLOCKED", revision, list(reasons), info)

    try:
        chain = migration_chain()
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return blocked("Missing alembic_version; no trusted history")
        with engine.connect() as connection:
            versions = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        if len(versions) != 1:
            return blocked("Expected exactly one revision")
        revision = versions[0]
        info.append(f"revision={revision}")
        if revision not in chain:
            return blocked("Unknown revision")
        profiles = load_profiles(base)
        manifest = reconciliation_manifest()
        if set(manifest["created_tables"]) != (
            set(profiles[TARGET].metadata.tables)
            - set(profiles["20260908_001"].metadata.tables)
        ):
            return blocked("Reconciliation manifest contradicts frozen profiles")
        matches = []
        comparisons = {}
        for candidate, expected in profiles.items():
            drift = check_drift(engine, expected)
            comparisons[candidate] = drift
            if not drift.errors:
                matches.append(candidate)
        if len(matches) != 1:
            return blocked(f"Expected one trusted schema match; got {matches}",
                           *comparisons[TARGET].errors)
        matched = matches[0]
        info.append(f"schema_matches={matched}; historical effects verified against frozen contract")
        if chain.index(matched) < chain.index(revision):
            return blocked("Schema is behind recorded revision")
        if matched == TARGET:
            drift = check_drift(engine, base)
            if drift.errors:
                return blocked(*drift.errors)
            info.extend(drift.warnings)
            return AdoptionResult(f"SAFE TO ADOPT TO {TARGET}", revision, [], info)
        if matched != revision:
            return blocked("Schema and version disagree; partial adoption is not supported")
        pending = chain[chain.index(revision) + 1:]
        return AdoptionResult(f"UPGRADE REQUIRED FROM {revision}", revision,
                              [f"Must execute real migrations: {', '.join(pending)}"], info)
    except Exception as exc:  # noqa: BLE001 -- fail closed and redact connection secrets.
        # Exception messages can contain credentials or SQL; report only the class.
        return blocked(f"Inspection could not complete ({type(exc).__name__}); no recommendation")


def main():
    from sqlalchemy import create_engine

    from app import models  # noqa: F401
    from app.core.config import get_settings
    from app.core.database import Base

    engine = create_engine(get_settings().DATABASE_URL)
    try:
        result = inspect_adoption(engine, Base)
        print(result.status)
        for line in result.info:
            print(f"INFO {line}")
        for line in result.reasons:
            print(f"ERROR {line}")
        return 0 if result.status.startswith("SAFE TO ADOPT") else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
