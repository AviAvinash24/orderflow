import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.jobs.expire_reservations import expire_stale_reservations
from app.tests.conftest import SEED_PRODUCT_ID, signup


@pytest.mark.asyncio
async def test_double_webhook_is_idempotent(
    live_client: AsyncClient,
    db,
    set_stock,
):
    await set_stock(SEED_PRODUCT_ID, available=5, reserved=0)

    token = await signup(live_client, f"wh-{uuid.uuid4().hex}@example.com")
    order = await live_client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [{"product_id": SEED_PRODUCT_ID, "quantity": 1}]},
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]
    event_id = f"evt-double-{uuid.uuid4().hex}"

    body = {
        "order_id": order_id,
        "gateway_event_id": event_id,
        "status": "succeeded",
    }
    r1 = await live_client.post("/webhooks/payment", json=body)
    r2 = await live_client.post("/webhooks/payment", json=body)
    assert r1.status_code == 200 and r1.json() == {"ok": True}
    assert r2.status_code == 200 and r2.json() == {"ok": True}

    status = await db.fetchval(
        "SELECT status FROM orders WHERE id = $1::uuid", order_id
    )
    payments = await db.fetchval(
        "SELECT COUNT(*) FROM payment_events WHERE gateway_event_id = $1",
        event_id,
    )
    outbox = await db.fetchval(
        """
        SELECT COUNT(*) FROM outbox_events
        WHERE event_type = 'order.paid'
          AND payload->>'order_id' = $1
        """,
        order_id,
    )
    assert status == "paid"
    assert payments == 1
    assert outbox == 1


@pytest.mark.asyncio
async def test_concurrent_buyers_only_one_wins_last_unit(
    live_client: AsyncClient,
    db,
    set_stock,
):
    await set_stock(SEED_PRODUCT_ID, available=1, reserved=0)

    t1 = await signup(live_client, f"buyer-a-{uuid.uuid4().hex}@example.com")
    t2 = await signup(live_client, f"buyer-b-{uuid.uuid4().hex}@example.com")
    payload = {"items": [{"product_id": SEED_PRODUCT_ID, "quantity": 1}]}

    async def place(token: str):
        return await live_client.post(
            "/orders",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )

    r1, r2 = await asyncio.gather(place(t1), place(t2))
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [201, 409], (r1.status_code, r1.text, r2.status_code, r2.text)

    row = await db.fetchrow(
        """
        SELECT quantity_available, quantity_reserved
        FROM inventory
        WHERE product_id = $1::uuid
        """,
        SEED_PRODUCT_ID,
    )
    assert row["quantity_available"] == 0
    assert row["quantity_reserved"] == 1


@pytest.mark.asyncio
async def test_expiry_releases_reserved_stock(
    live_client: AsyncClient,
    db,
    set_stock,
):
    await set_stock(SEED_PRODUCT_ID, available=3, reserved=0)

    token = await signup(live_client, f"exp-{uuid.uuid4().hex}@example.com")
    order = await live_client.post(
        "/orders",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [{"product_id": SEED_PRODUCT_ID, "quantity": 1}]},
    )
    assert order.status_code == 201, order.text
    order_id = order.json()["id"]

    before = await db.fetchrow(
        """
        SELECT quantity_available, quantity_reserved
        FROM inventory
        WHERE product_id = $1::uuid
        """,
        SEED_PRODUCT_ID,
    )
    assert before["quantity_available"] == 2
    assert before["quantity_reserved"] == 1

    # Make reservation immediately eligible for expiry
    await db.execute(
        """
        UPDATE orders
        SET expires_at = $2
        WHERE id = $1::uuid
        """,
        order_id,
        datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    # Use the same pool the job expects
    from app.core.db import close_db, connect_db

    await connect_db()
    try:
        n = await expire_stale_reservations()
    finally:
        await close_db()

    assert n >= 1

    status = await db.fetchval(
        "SELECT status FROM orders WHERE id = $1::uuid", order_id
    )
    after = await db.fetchrow(
        """
        SELECT quantity_available, quantity_reserved
        FROM inventory
        WHERE product_id = $1::uuid
        """,
        SEED_PRODUCT_ID,
    )
    assert status == "expired"
    assert after["quantity_available"] == 3
    assert after["quantity_reserved"] == 0