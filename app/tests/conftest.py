import os

import asyncpg
import pytest
import pytest_asyncio
from httpx import AsyncClient

# Host-side defaults (docker-compose ports)
os.environ.setdefault("POSTGRES_USER", "orderflow")
os.environ.setdefault("POSTGRES_PASSWORD", "orderflow")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "orderflow")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

BASE_URL = os.environ.get("ORDERFLOW_BASE_URL", "http://localhost:8000")
SEED_PRODUCT_ID = "11111111-1111-1111-1111-111111111111"


def _database_url() -> str:
    return (
        f"postgresql://{os.environ['POSTGRES_USER']}:"
        f"{os.environ['POSTGRES_PASSWORD']}@"
        f"{os.environ['POSTGRES_HOST']}:"
        f"{os.environ['POSTGRES_PORT']}/"
        f"{os.environ['POSTGRES_DB']}"
    )


@pytest_asyncio.fixture
async def client():
    """In-process ASGI client (auth unit tests)."""
    from httpx import ASGITransport

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def live_client():
    """HTTP client against running docker API."""
    async with AsyncClient(base_url=BASE_URL, timeout=30.0) as ac:
        health = await ac.get("/health")
        assert health.status_code == 200, "API not up — run: docker compose up -d"
        yield ac


@pytest_asyncio.fixture
async def db():
    conn = await asyncpg.connect(_database_url())
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def set_stock(db):
    async def _set(product_id: str, available: int, reserved: int = 0) -> None:
        await db.execute(
            """
            UPDATE inventory
            SET quantity_available = $2,
                quantity_reserved = $3
            WHERE product_id = $1::uuid
            """,
            product_id,
            available,
            reserved,
        )

    return _set


async def signup(client: AsyncClient, email: str, password: str = "password123") -> str:
    res = await client.post(
        "/auth/signup",
        json={"email": email, "password": password},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]