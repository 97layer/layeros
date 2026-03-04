"""User schemas for request/response validation."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8, max_length=100)


class UserLogin(BaseModel):
    """User login schema."""
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserResponse(UserBase):
    """User response schema."""
    id: int
    tenant_id: str
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AddressBase(BaseModel):
    """Base address schema."""
    recipient_name: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=20)
    postal_code: str = Field(..., max_length=10)
    address_line1: str = Field(..., max_length=200)
    address_line2: Optional[str] = None
    city: str = Field(..., max_length=50)
    is_default: bool = False


class AddressCreate(AddressBase):
    """Address creation schema."""
    pass


class AddressResponse(AddressBase):
    """Address response schema."""
    id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """JWT token payload data."""
    user_id: Optional[int] = None
    email: Optional[str] = None
    tenant_id: Optional[str] = None
