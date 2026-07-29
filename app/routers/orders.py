from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.db import get_pool
from app.core.deps import CurrentUser, get_current_user
from app.schemas.orders import CreateOrderRequest, OrderItemResponse, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])

RESERVATION_MINUTES = 10


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: CreateOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESERVATION_MINUTES)

    async with pool.acquire() as conn:
        async with conn.transaction():
            product = await conn.fetchrow(
                "SELECT id, price FROM products WHERE id = $1::uuid",
                body.product_id,
            )
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product not found",
                )

            reserved = await conn.fetchrow(
                """
                UPDATE inventory
                SET quantity_available = quantity_available - $2,
                    quantity_reserved = quantity_reserved + $2
                WHERE product_id = $1::uuid
                  AND quantity_available >= $2
                RETURNING product_id
                """,
                body.product_id,
                body.quantity,
            )
            if reserved is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Insufficient stock",
                )

            unit_price = Decimal(str(product["price"]))
            total_amount = unit_price * body.quantity

            order = await conn.fetchrow(
                """
                INSERT INTO orders (user_id, status, total_amount, expires_at)
                VALUES ($1::uuid, 'placed', $2, $3)
                RETURNING id, status, total_amount, expires_at
                """,
                current_user.id,
                total_amount,
                expires_at,
            )

            await conn.execute(
                """
                INSERT INTO order_items (
                    order_id, product_id, quantity, unit_price_at_purchase
                )
                VALUES ($1, $2::uuid, $3, $4)
                """,
                order["id"],
                body.product_id,
                body.quantity,
                unit_price,
            )

    return OrderResponse(
        id=str(order["id"]),
        status=order["status"],
        total_amount=order["total_amount"],
        expires_at=order["expires_at"],
        items=[
            OrderItemResponse(
                product_id=body.product_id,
                quantity=body.quantity,
                unit_price_at_purchase=unit_price,
            )
        ],
    )