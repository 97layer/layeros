"""Cart API endpoints using Redis sessions."""
from typing import Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from ..models import get_db, Product
from ..schemas import CartItemAdd, CartItemUpdate, CartResponse, CartItemResponse
from ..utils import get_public_tenant_id, redis_client

router = APIRouter(prefix="/cart", tags=["Cart"])


def get_session_id(x_session_id: Optional[str] = Header(None)) -> str:
    """Get or validate session ID from header."""
    if not x_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Session-ID header required"
        )
    return x_session_id


def get_tenant_scoped_session_id(
    session_id: str = Depends(get_session_id),
    tenant_id: str = Depends(get_public_tenant_id),
) -> str:
    """Namespace cart session by tenant to prevent cross-tenant collisions."""
    return f"{tenant_id}:{session_id}"


@router.get("", response_model=CartResponse)
def get_cart(
    scoped_session_id: str = Depends(get_tenant_scoped_session_id),
    db: Session = Depends(get_db)
):
    """Get cart contents for session."""
    cart_items = redis_client.get_cart(scoped_session_id) or []

    # Enrich with product details
    response_items = []
    subtotal = Decimal("0.00")

    for item in cart_items:
        product = db.query(Product).filter(Product.id == item["product_id"]).first()
        if not product:
            continue

        item_subtotal = product.price * item["quantity"]
        subtotal += item_subtotal

        response_items.append(
            CartItemResponse(
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                product_image=product.images[0]["url"] if product.images else None,
                price=product.price,
                quantity=item["quantity"],
                subtotal=item_subtotal
            )
        )

    return CartResponse(
        items=response_items,
        subtotal=subtotal,
        total_items=len(response_items)
    )


@router.post("/items", status_code=status.HTTP_201_CREATED)
def add_to_cart(
    item: CartItemAdd,
    scoped_session_id: str = Depends(get_tenant_scoped_session_id),
    db: Session = Depends(get_db)
):
    """Add item to cart."""
    # Verify product exists and is available
    product = db.query(Product).filter(Product.id == item.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    if not product.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product is not available"
        )

    # Check stock
    if product.track_inventory and product.stock_quantity < item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.stock_quantity} items available"
        )

    # Add to cart
    redis_client.add_item(scoped_session_id, item.product_id, item.quantity)

    return {"message": "Item added to cart"}


@router.patch("/items/{product_id}")
def update_cart_item(
    product_id: int,
    update: CartItemUpdate,
    scoped_session_id: str = Depends(get_tenant_scoped_session_id),
    db: Session = Depends(get_db)
):
    """Update cart item quantity."""
    if update.quantity > 0:
        # Verify product and stock
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        if product.track_inventory and product.stock_quantity < update.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only {product.stock_quantity} items available"
            )

    redis_client.update_item(scoped_session_id, product_id, update.quantity)

    return {"message": "Cart updated"}


@router.delete("/items/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_cart(
    product_id: int,
    scoped_session_id: str = Depends(get_tenant_scoped_session_id)
):
    """Remove item from cart."""
    redis_client.remove_item(scoped_session_id, product_id)
    return None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_cart(scoped_session_id: str = Depends(get_tenant_scoped_session_id)):
    """Clear all items from cart."""
    redis_client.clear_cart(scoped_session_id)
    return None
