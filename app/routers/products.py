from fastapi import APIRouter, HTTPException, status

from app.core.db import get_pool
from app.schemas.products import ProductResponse

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductResponse])
async def list_products():
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT
            p.id,
            p.name,
            p.price,
            p.sku,
            COALESCE(i.quantity_available, 0) AS quantity_available
        FROM products p
        LEFT JOIN inventory i ON i.product_id = p.id
        ORDER BY p.name
        """
    )
    return [
        ProductResponse(
            id=str(row["id"]),
            name=row["name"],
            price=row["price"],
            sku=row["sku"],
            quantity_available=row["quantity_available"],
        )
        for row in rows
    ]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    pool = get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            p.id,
            p.name,
            p.price,
            p.sku,
            COALESCE(i.quantity_available, 0) AS quantity_available
        FROM products p
        LEFT JOIN inventory i ON i.product_id = p.id
        WHERE p.id = $1::uuid
        """,
        product_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return ProductResponse(
        id=str(row["id"]),
        name=row["name"],
        price=row["price"],
        sku=row["sku"],
        quantity_available=row["quantity_available"],
    )