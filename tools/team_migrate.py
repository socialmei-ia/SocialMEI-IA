"""Migrate only the isolated team database before allowing the API to start."""

import re
from pathlib import Path

from database import connect


def migrate(directory=Path("/migrations")):
    files = sorted(directory.glob("*.sql"))
    if not files or any(
        not re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", p.name) for p in files
    ):
        raise RuntimeError("Lista de migrations ausente ou inválida.")
    # One transaction + advisory lock prevents overlapping startup migrations.
    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(72426001)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS socialmei")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS socialmei.schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT version FROM socialmei.schema_migrations")
        }
        for file in files:
            if file.name in applied:
                continue
            conn.execute(file.read_text(), prepare=False)
            conn.execute(
                "INSERT INTO socialmei.schema_migrations (version) VALUES (%s)",
                (file.name,),
            )
            print(f"Aplicada: {file.name}")
    print("Banco da equipe atualizado.")


if __name__ == "__main__":
    migrate()
