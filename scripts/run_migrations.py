import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


async def run_migrations():
    conn = await asyncpg.connect(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
    )

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    applied = {
        row["filename"]
        for row in await conn.fetch("SELECT filename FROM schema_migrations")
    }

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for path in migration_files:
        if path.name in applied:
            print(f"skip  {path.name} (already applied)")
            continue

        sql = path.read_text()
        async with conn.transaction():
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1)",
                path.name,
            )
        print(f"apply {path.name}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())