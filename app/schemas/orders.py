from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(gt=0)


class CreateOrderRequest(BaseModel):
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemResponse(BaseModel):
    product_id: str
    quantity: int
    unit_price_at_purchase: Decimal


class OrderResponse(BaseModel):
    id: str
    status: str
    total_amount: Decimal
    expires_at: datetime | None
    items: list[OrderItemResponse]