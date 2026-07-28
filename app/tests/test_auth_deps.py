from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import JWT_ALGORITHM, JWT_SECRET
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient):
    res = await client.get("/me")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_with_garbage_token_returns_401(client: AsyncClient):
    res = await client.get(
        "/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_with_expired_token_returns_401(client: AsyncClient):
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "email": "gone@example.com",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    res = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token_returns_identity(client: AsyncClient):
    user_id = "22222222-2222-2222-2222-222222222222"
    email = "ok@example.com"
    token = create_access_token(user_id, email)

    res = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == user_id
    assert body["email"] == email