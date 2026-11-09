from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Device, User
from .security import decode_access_token, hash_device_key

_bearer = HTTPBearer(auto_error=False)


def user_from_token(db: Session, token: str | None) -> User | None:
    payload = decode_access_token(token) if token else None
    if not payload:
        return None
    user = db.scalars(select(User).where(User.operator_id == payload.get("sub"))).first()
    if not user or not user.is_active or payload.get("tv", 0) != user.token_version:
        return None  # deactivated, or password/role changed since this token was issued
    return user


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    user = user_from_token(db, creds.credentials if creds else None)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return dep


operator_or_admin = require_roles("admin", "operator")
admin_only = require_roles("admin")


def current_device(x_device_key: str | None = Header(default=None), db: Session = Depends(get_db)) -> Device:
    if not x_device_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing device key")
    device = db.scalars(select(Device).where(Device.api_key_hash == hash_device_key(x_device_key))).first()
    if not device:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device key")
    return device
