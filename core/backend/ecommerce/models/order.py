"""Order model for order management and fulfillment."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, Numeric, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(str, Enum):
    """Payment status enumeration."""
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class Order(Base):
    """Order model."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(64), index=True, nullable=False, default="woohwahae")
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Order status
    status = Column(String(20), default=OrderStatus.PENDING.value, index=True)
    payment_status = Column(String(20), default=PaymentStatus.PENDING.value)

    # Pricing
    subtotal = Column(Numeric(10, 2), nullable=False)
    shipping_fee = Column(Numeric(10, 2), default=0)
    discount_amount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), nullable=False)

    # Shipping information
    shipping_address = Column(JSON, nullable=False)
    shipping_method = Column(String(50), nullable=True)
    tracking_number = Column(String(100), nullable=True)

    # Payment information
    payment_method = Column(String(50), nullable=True)
    payment_transaction_id = Column(String(100), nullable=True)
    payment_gateway = Column(String(50), nullable=True)  # "stripe" | "tosspayments"

    # Customer notes
    customer_note = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    paid_at = Column(DateTime, nullable=True)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """Order line item."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # Product snapshot at time of order
    product_name = Column(String(200), nullable=False)
    product_sku = Column(String(50), nullable=False)
    product_image = Column(String(500), nullable=True)

    # Pricing
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
