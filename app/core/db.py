import asyncpg
from app.core.config import DATABASE_URL

pool: asyncpg.Pool | None = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

async def close_db():
    global pool
    if pool:
        await pool.close()
        pool = None

def get_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("DB pool is not initialized")
    return pool