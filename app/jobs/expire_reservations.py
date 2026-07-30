import asyncio
import logging

from app.core.config import EXPIRY_JOB_INTERVAL_SECONDS
from app.core.db import get_pool

logger = logging.getLogger(__name__)


async def expire_stale_reservations() -> int:
    """
    Claim expired placed orders, mark them expired, release reserved stock.
    Returns how many orders were expired in this pass.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1) Atomically claim rows — SKIP LOCKED so concurrent jobs don't clash
            expired = await conn.fetch(
                """
                UPDATE orders
                SET status = 'expired'
                WHERE id IN (
                    SELECT id
                    FROM orders
                    WHERE status = 'placed'
                      AND expires_at IS NOT NULL
                      AND expires_at <= now()
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 100
                )
                RETURNING id
                """
            )
            if not expired:
                return 0

            expired_ids = [row["id"] for row in expired]

            # 2) Sum quantities per product, then release once per product
            await conn.execute(
                """
                WITH to_release AS (
                    SELECT oi.product_id, SUM(oi.quantity)::int AS qty
                    FROM order_items oi
                    WHERE oi.order_id = ANY($1::uuid[])
                    GROUP BY oi.product_id
                )
                UPDATE inventory i
                SET quantity_available = quantity_available + r.qty,
                    quantity_reserved  = quantity_reserved  - r.qty
                FROM to_release r
                WHERE i.product_id = r.product_id
                """,
                expired_ids,
            )

            return len(expired_ids)


async def expiry_loop(stop: asyncio.Event) -> None:
    """Poll forever until stop is set (API shutdown)."""
    logger.info(
        "Reservation expiry job started (interval=%ss)",
        EXPIRY_JOB_INTERVAL_SECONDS,
    )
    while not stop.is_set():
        try:
            n = await expire_stale_reservations()
            if n:
                logger.info("Expired %s reservation(s) and released stock", n)
        except Exception:
            logger.exception("Reservation expiry job failed")

        try:
            await asyncio.wait_for(stop.wait(), timeout=EXPIRY_JOB_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass  # interval elapsed → run again