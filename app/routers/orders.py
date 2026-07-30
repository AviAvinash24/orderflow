from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.db import get_pool
from app.core.deps import CurrentUser, get_current_user
from app.schemas.orders import CreateOrderRequest, OrderItemResponse, OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])

from app.core.config import RESERVATION_MINUTES


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: CreateOrderRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    pool = get_pool()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESERVATION_MINUTES)

    # Deterministic lock order: same product row order for every concurrent order
    # → avoids A locks Mouse→Keyboard while B locks Keyboard→Mouse (deadlock).
    items = sorted(body.items, key=lambda i: i.product_id)

    async with pool.acquire() as conn:
        async with conn.transaction():
            reserved_items: list[OrderItemResponse] = []
            total_amount = Decimal("0")

            for item in items:
                product = await conn.fetchrow(
                    "SELECT id, price FROM products WHERE id = $1::uuid",
                    item.product_id,
                )
                if product is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Product not found: {item.product_id}",
                    )

                # Atomic check-and-decrement: only one concurrent UPDATE wins
                # the last unit. Losers get 0 rows → 409. Never goes negative.
                reserved = await conn.fetchrow(
                    """
                    UPDATE inventory
                    SET quantity_available = quantity_available - $2,
                        quantity_reserved = quantity_reserved + $2
                    WHERE product_id = $1::uuid
                      AND quantity_available >= $2
                    RETURNING product_id, quantity_available, quantity_reserved
                    """,
                    item.product_id,
                    item.quantity,
                )
                if reserved is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Insufficient stock for product: {item.product_id}",
                    )

                unit_price = Decimal(str(product["price"]))
                total_amount += unit_price * item.quantity
                reserved_items.append(
                    OrderItemResponse(
                        product_id=item.product_id,
                        quantity=item.quantity,
                        unit_price_at_purchase=unit_price,
                    )
                )

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

            for line in reserved_items:
                await conn.execute(
                    """
                    INSERT INTO order_items (
                        order_id, product_id, quantity, unit_price_at_purchase
                    )
                    VALUES ($1, $2::uuid, $3, $4)
                    """,
                    order["id"],
                    line.product_id,
                    line.quantity,
                    line.unit_price_at_purchase,
                )

    return OrderResponse(
        id=str(order["id"]),
        status=order["status"],
        total_amount=order["total_amount"],
        expires_at=order["expires_at"],
        items=reserved_items,
    )