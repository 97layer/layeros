"""Authentication API endpoints."""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..models import get_db, User
from ..schemas import UserCreate, UserResponse, Token
from ..utils import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    get_authenticated_tenant_id,
    get_public_tenant_id,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    tenant_id: str = Depends(get_public_tenant_id),
    db: Session = Depends(get_db),
):
    """Register new user account."""
    # Check if email already exists
    existing_user = db.query(User).filter(
        User.email == user_data.email,
        User.tenant_id == tenant_id,
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    user = User(
        tenant_id=tenant_id,
        email=user_data.email,
        full_name=user_data.full_name,
        phone=user_data.phone,
        hashed_password=get_password_hash(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    tenant_id: str = Depends(get_public_tenant_id),
    db: Session = Depends(get_db)
):
    """Login and get access token."""
    # Find user by email (username field)
    user = db.query(User).filter(
        User.email == form_data.username,
        User.tenant_id == tenant_id,
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "tenant_id": tenant_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user information."""
    return current_user


@router.post("/refresh", response_model=Token)
def refresh_token(
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_authenticated_tenant_id),
):
    """Refresh access token."""
    access_token = create_access_token(
        data={"sub": current_user.id, "email": current_user.email, "tenant_id": tenant_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }
