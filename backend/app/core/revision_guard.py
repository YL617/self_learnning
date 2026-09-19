"""Read-only startup guard; migration is an explicit deployment step."""

from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "alembic"


class SchemaRevisionError(RuntimeError):
    pass


def expected_head(directory=MIGRATION_DIR) -> str:
    script = ScriptDirectory(str(directory))
    if len(script.get_heads()) != 1 or len(script.get_bases()) != 1:
        raise SchemaRevisionError("Expected a single migration base and head")
    previous = None
    for revision in reversed(list(script.walk_revisions())):
        if (revision.down_revision != previous or revision.dependencies
                or revision.is_branch_point or revision.is_merge_point):
            raise SchemaRevisionError("Migration history must be linear")
        previous = revision.revision
    return script.get_current_head()


def require_schema_revision(engine) -> str:
    try:
        head = expected_head()
        with engine.connect() as connection:
            if not inspect(connection).has_table("alembic_version"):
                raise SchemaRevisionError("Database has no revision; run the deployment migration step")
            versions = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        if versions != [head]:
            raise SchemaRevisionError(f"Database revision must equal code head {head}; startup refused")
        return head
    except SchemaRevisionError:
        raise
    except Exception as exc:  # noqa: BLE001 -- fail closed without exposing connection credentials.
        raise SchemaRevisionError(
            f"Revision verification failed ({type(exc).__name__}); startup refused"
        ) from None


def main() -> int:
    from app.core.database import engine

    try:
        print(f"REVISION VERIFIED {require_schema_revision(engine)}")
        return 0
    except SchemaRevisionError as exc:
        print(f"ERROR {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
