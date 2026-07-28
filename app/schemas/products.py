from decimal import Decimal

from pydantic import BaseModel


class ProductResponse(BaseModel):
    id: str
    name: str
    price: Decimal
    sku: str
    quantity_available: int