"""JWT authentication utilities."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..config import settings
from ..models import get_db, User
from ..schemas import TokenData
from .tenant import normalize_tenant_id, resolve_public_tenant_id

# Configuration
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_EXPIRE_MINUTES

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if "sub" in to_encode and to_encode["sub"] is not None:
        # RFC7519 subject claim is string; normalize to avoid provider-specific decode failures.
        to_encode["sub"] = str(to_encode["sub"])
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub_claim = payload.get("sub")
        email: str = payload.get("email")
        tenant_id: str = payload.get("tenant_id")
        if sub_claim is None:
            return None
        try:
            user_id = int(sub_claim)
        except (TypeError, ValueError):
            return None
        normalized_tenant = None
        if tenant_id:
            normalized_tenant = normalize_tenant_id(tenant_id)
        return TokenData(user_id=user_id, email=email, tenant_id=normalized_tenant)
    except (JWTError, ValueError):
        return None


def get_current_token_data(
    token: str = Depends(oauth2_scheme),
) -> TokenData:
    """Return validated token payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None or token_data.user_id is None:
        raise credentials_exception

    return token_data


def get_requested_tenant_id(
    request: Request,
) -> Optional[str]:
    """Return normalized tenant id from request header when present."""
    header_value = request.headers.get(settings.TENANT_HEADER)
    if not header_value:
        return None
    return normalize_tenant_id(header_value)


def get_public_tenant_id(
    requested_tenant_id: Optional[str] = Depends(get_requested_tenant_id),
) -> str:
    """Resolve tenant for unauthenticated/public endpoints."""
    return resolve_public_tenant_id(requested_tenant_id)


def get_authenticated_tenant_id(
    token_data: TokenData = Depends(get_current_token_data),
    requested_tenant_id: Optional[str] = Depends(get_requested_tenant_id),
) -> str:
    """Resolve tenant for authenticated endpoints and enforce claim/header match."""
    token_tenant = token_data.tenant_id or normalize_tenant_id(settings.DEFAULT_TENANT_ID)
    if requested_tenant_id and requested_tenant_id != token_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch between token and request header",
        )
    return requested_tenant_id or token_tenant


def get_current_user(
    token_data: TokenData = Depends(get_current_token_data),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token."""
    tenant_id = token_data.tenant_id or normalize_tenant_id(settings.DEFAULT_TENANT_ID)
    user = db.query(User).filter(
        User.id == token_data.user_id,
        User.tenant_id == tenant_id,
    ).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    setattr(user, "tenant_id", token_data.tenant_id or normalize_tenant_id(settings.DEFAULT_TENANT_ID))
    return user


def get_current_active_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Verify user has admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user
