import json
import logging

from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, status

from app.core.db import get_pool
from app.schemas.webhooks import PaymentWebhookRequest, PaymentWebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/payment",
    response_model=PaymentWebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def payment_webhook(body: PaymentWebhookRequest) -> PaymentWebhookResponse:
    """
    Idempotent payment callback.
    Always 200 — even for unknown/late orders — so the gateway does not retry-storm.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            order = await conn.fetchrow(
                """
                SELECT id, status
                FROM orders
                WHERE id = $1::uuid
                FOR UPDATE
                """,
                body.order_id,
            )
            if order is None:
                logger.warning(
                    "payment webhook for unknown order_id=%s gateway_event_id=%s",
                    body.order_id,
                    body.gateway_event_id,
                )
                return PaymentWebhookResponse()

            try:
                await conn.execute(
                    """
                    INSERT INTO payment_events (order_id, gateway_event_id, status)
                    VALUES ($1, $2, $3::payment_status)
                    """,
                    order["id"],
                    body.gateway_event_id,
                    body.status,
                )
            except UniqueViolationError:
                # Same gateway event delivered twice — already applied.
                return PaymentWebhookResponse()

            if body.status == "succeeded":
                if order["status"] == "placed":
                    await conn.execute(
                        """
                        UPDATE orders
                        SET status = 'paid'
                        WHERE id = $1
                          AND status = 'placed'
                        """,
                        order["id"],
                    )
                    await conn.execute(
                        """
                        INSERT INTO outbox_events (event_type, payload)
                        VALUES ($1, $2::jsonb)
                        """,
                        "order.paid",
                        json.dumps(
                            {
                                "order_id": str(order["id"]),
                                "gateway_event_id": body.gateway_event_id,
                            }
                        ),
                    )
                else:
                    logger.warning(
                        "late/ignored succeeded payment order_id=%s "
                        "status=%s gateway_event_id=%s",
                        order["id"],
                        order["status"],
                        body.gateway_event_id,
                    )
            else:
                logger.info(
                    "failed payment recorded order_id=%s gateway_event_id=%s",
                    order["id"],
                    body.gateway_event_id,
                )

    return PaymentWebhookResponse()