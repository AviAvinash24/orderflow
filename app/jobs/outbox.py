import asyncio
import json
import logging
from typing import Any

import asyncpg

from app.core.config import DATABASE_URL, OUTBOX_BATCH_SIZE

logger = logging.getLogger(__name__)


def _payload_dict(payload: Any) -> dict:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return dict(payload)


async def _handle_event(event_type: str, payload: dict) -> None:
    """Side-effect stub — swap for email/SMS later. Must be safe to retry."""
    if event_type == "order.paid":
        logger.info(
            "outbox handled order.paid order_id=%s gateway_event_id=%s",
            payload.get("order_id"),
            payload.get("gateway_event_id"),
        )
        return
    logger.warning("outbox unknown event_type=%s payload=%s", event_type, payload)


async def _process_outbox_batch_async() -> int:
    """
    Claim pending outbox rows, handle them, mark processed.
    Returns how many events were processed in this pass.
    """
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT id, event_type, payload
                FROM outbox_events
                WHERE status = 'pending'
                ORDER BY created_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT $1
                """,
                OUTBOX_BATCH_SIZE,
            )
            if not rows:
                return 0

            for row in rows:
                payload = _payload_dict(row["payload"])
                await _handle_event(row["event_type"], payload)
                await conn.execute(
                    """
                    UPDATE outbox_events
                    SET status = 'processed'
                    WHERE id = $1
                      AND status = 'pending'
                    """,
                    row["id"],
                )

            return len(rows)
    finally:
        await conn.close()


def process_outbox_batch() -> int:
    """RQ job entrypoint (sync)."""
    n = asyncio.run(_process_outbox_batch_async())
    if n:
        logger.info("Processed %s outbox event(s)", n)
    return n