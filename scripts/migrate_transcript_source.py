"""One-off migration: add provenance columns to the transcripts table.

No Alembic in this project, so this is a plain idempotent ADD COLUMN against the
configured SQLite database. Safe to run repeatedly — it checks first.

    python -m scripts.migrate_transcript_source
"""

import sys

from sqlalchemy import text

from app.database import engine


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}


def migrate() -> None:
    with engine.begin() as conn:
        cols = _columns(conn, "transcripts")
        if not cols:
            print("transcripts table does not exist yet; nothing to migrate "
                  "(it will be created with the new columns).")
            return
        added = []
        if "source" not in cols:
            conn.execute(text("ALTER TABLE transcripts ADD COLUMN source VARCHAR(20)"))
            added.append("source")
        if "is_auto" not in cols:
            conn.execute(text("ALTER TABLE transcripts ADD COLUMN is_auto BOOLEAN DEFAULT 0"))
            added.append("is_auto")
        if added:
            print(f"Added columns: {', '.join(added)}")
        else:
            print("Columns already present; nothing to do.")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
