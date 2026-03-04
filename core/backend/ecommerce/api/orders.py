"""Order API endpoints."""
from datetime import datetime, timezone
from decimal import Decimal
from math import ceil
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..models import get_db, Order, OrderItem, Product, User, OrderStatus, PaymentStatus
from ..schemas import OrderCreate, OrderUpdate, OrderResponse, OrderListResponse
from ..utils import get_authenticated_tenant_id, get_current_user, get_current_active_admin

router = APIRouter(prefix="/orders", tags=["Orders"])


def generate_order_number() -> str:
    """Generate unique order number."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"WH{timestamp}{secrets.randbelow(10000):04d}"


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order_data: OrderCreate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create new order from cart or direct items."""
    # Calculate totals
    subtotal = Decimal("0.00")
    order_items = []

    for item in order_data.items:
        product_query = db.query(Product).filter(Product.id == item.product_id)
        product = product_query.with_for_update().first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item.product_id} not found"
            )

        if not product.is_published:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {product.name} is not available"
            )

        # Check stock
        if product.track_inventory and product.stock_quantity < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for {product.name}"
            )

        item_subtotal = product.price * item.quantity
        subtotal += item_subtotal

        order_items.append({
            "product": product,
            "quantity": item.quantity,
            "unit_price": product.price,
            "subtotal": item_subtotal
        })

    # Calculate shipping (flat rate for now)
    shipping_fee = Decimal("3000.00") if subtotal < Decimal("50000.00") else Decimal("0.00")
    total = subtotal + shipping_fee

    # Create order
    order = Order(
        tenant_id=tenant_id,
        order_number=generate_order_number(),
        user_id=current_user.id,
        subtotal=subtotal,
        shipping_fee=shipping_fee,
        total=total,
        shipping_address=order_data.shipping_address,
        shipping_method=order_data.shipping_method,
        payment_method=order_data.payment_method,
        customer_note=order_data.customer_note,
    )
    db.add(order)
    db.flush()

    # Create order items
    for item_data in order_items:
        product = item_data["product"]
        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            product_image=product.images[0]["url"] if product.images else None,
            unit_price=item_data["unit_price"],
            quantity=item_data["quantity"],
            subtotal=item_data["subtotal"]
        )
        db.add(order_item)

        # Reduce stock
        if product.track_inventory:
            product.stock_quantity -= item_data["quantity"]

    db.commit()
    db.refresh(order)

    return order


@router.get("", response_model=OrderListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's orders."""
    query = db.query(Order).filter(
        Order.user_id == current_user.id,
        Order.tenant_id == tenant_id,
    )

    if status:
        query = query.filter(Order.status == status)

    query = query.order_by(Order.created_at.desc())

    total = query.count()
    total_pages = ceil(total / page_size)
    offset = (page - 1) * page_size

    orders = query.offset(offset).limit(page_size).all()

    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get order details."""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
        Order.tenant_id == tenant_id,
    ).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    return order


@router.patch("/{order_id}", response_model=OrderResponse)
def update_order(
    order_id: int,
    order_data: OrderUpdate,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    db: Session = Depends(get_db),
    admin: None = Depends(get_current_active_admin)
):
    """Update order (admin only)."""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.tenant_id == tenant_id,
    ).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Update fields
    update_data = order_data.dict(exclude_unset=True)

    # Handle status transitions
    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == OrderStatus.SHIPPED.value and not order.shipped_at:
            order.shipped_at = datetime.now(timezone.utc)
        elif new_status == OrderStatus.DELIVERED.value and not order.delivered_at:
            order.delivered_at = datetime.now(timezone.utc)
        elif new_status == OrderStatus.CANCELLED.value and not order.cancelled_at:
            order.cancelled_at = datetime.now(timezone.utc)

    if "payment_status" in update_data:
        if update_data["payment_status"] == PaymentStatus.PAID.value and not order.paid_at:
            order.paid_at = datetime.now(timezone.utc)

    for field, value in update_data.items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)

    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_order(
    order_id: int,
    tenant_id: str = Depends(get_authenticated_tenant_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel order (before processing)."""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
        Order.tenant_id == tenant_id,
    ).first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    if order.status not in [OrderStatus.PENDING.value, OrderStatus.CONFIRMED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel order in current status"
        )

    order.status = OrderStatus.CANCELLED.value
    order.cancelled_at = datetime.now(timezone.utc)

    # Restore stock
    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product and product.track_inventory:
            product.stock_quantity += item.quantity

    db.commit()
    return None
