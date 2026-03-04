"""Database initialization script.

Run this script to create all tables in the database.
For production, use Alembic migrations instead.
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import init_db, engine, User, Product
from utils import get_password_hash
from config import settings


def create_admin_user(db):
    """Create default admin user."""
    admin_email = os.getenv("ECOMMERCE_ADMIN_EMAIL", "").strip()
    admin_password = os.getenv("ECOMMERCE_ADMIN_PASSWORD", "").strip()

    if not admin_email or not admin_password:
        print("⚠️  ECOMMERCE_ADMIN_EMAIL / ECOMMERCE_ADMIN_PASSWORD 미설정: 관리자 시드 건너뜀")
        return
    if len(admin_password) < 12:
        raise RuntimeError("ECOMMERCE_ADMIN_PASSWORD는 최소 12자 이상이어야 합니다.")

    admin = db.query(User).filter(
        User.email == admin_email,
        User.tenant_id == settings.DEFAULT_TENANT_ID,
    ).first()
    if not admin:
        admin = User(
            tenant_id=settings.DEFAULT_TENANT_ID,
            email=admin_email,
            full_name="WOOHWAHAE Admin",
            hashed_password=get_password_hash(admin_password),
            is_active=True,
            is_verified=True,
            is_admin=True
        )
        db.add(admin)
        db.commit()
        print(f"✓ Created admin user: {admin_email}")
    else:
        print("✓ Admin user already exists")


def create_sample_products(db):
    """Create sample products for testing."""
    existing = db.query(Product).filter(Product.sku == "WH-HAIR-001").first()
    if existing:
        print("✓ Sample products already exist")
        return

    sample_products = [
        {
            "sku": "WH-HAIR-001",
            "name": "헤어 오일 30ml",
            "slug": "hair-oil-30ml",
            "description": "천연 성분으로 만든 헤어 오일. 머릿결을 부드럽고 윤기있게 가꿔줍니다.",
            "short_description": "자연에서 온 머릿결 케어",
            "price": 28000,
            "compare_at_price": 35000,
            "stock_quantity": 50,
            "category": "hair-care",
            "tags": ["natural", "handmade", "bestseller"],
            "images": [
                {"url": "/images/products/hair-oil-01.jpg", "alt": "헤어 오일 정면"},
                {"url": "/images/products/hair-oil-02.jpg", "alt": "헤어 오일 측면"}
            ],
            "is_published": True,
            "is_featured": True,
            "meta_title": "천연 헤어 오일 30ml | WOOHWAHAE",
            "meta_description": "자연에서 온 머릿결 케어. 천연 성분 헤어 오일."
        },
        {
            "sku": "WH-HAIR-002",
            "name": "헤어 밤 50ml",
            "slug": "hair-balm-50ml",
            "description": "수분과 영양을 동시에 공급하는 헤어 밤. 손상된 모발을 집중 케어합니다.",
            "short_description": "촉촉한 머릿결을 위한",
            "price": 32000,
            "compare_at_price": 40000,
            "stock_quantity": 30,
            "category": "hair-care",
            "tags": ["natural", "moisturizing"],
            "images": [
                {"url": "/images/products/hair-balm-01.jpg", "alt": "헤어 밤"}
            ],
            "is_published": True,
            "is_featured": False
        },
        {
            "sku": "WH-SET-001",
            "name": "헤어 케어 세트",
            "slug": "hair-care-set",
            "description": "헤어 오일과 헤어 밤이 함께하는 완벽한 케어 세트",
            "short_description": "완벽한 헤어 케어 루틴",
            "price": 54000,
            "compare_at_price": 67000,
            "stock_quantity": 20,
            "category": "sets",
            "tags": ["natural", "gift", "value"],
            "images": [
                {"url": "/images/products/set-01.jpg", "alt": "헤어 케어 세트"}
            ],
            "is_published": True,
            "is_featured": True
        }
    ]

    for product_data in sample_products:
        product = Product(**product_data)
        db.add(product)

    db.commit()
    print(f"✓ Created {len(sample_products)} sample products")


def main():
    """Initialize database with tables and sample data."""
    print("🔄 Initializing database...")

    # Create all tables
    print("Creating tables...")
    init_db()
    print("✓ Tables created")

    # Create sample data
    from models.base import SessionLocal
    db = SessionLocal()

    try:
        create_admin_user(db)
        create_sample_products(db)
        print("\n✅ Database initialization complete!")
        print("\n📝 Next steps:")
        print("   1. Start Redis: redis-server")
        print("   2. Run API: uvicorn main:app --reload")
        print("   3. Visit docs: http://localhost:8000/api/docs")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
