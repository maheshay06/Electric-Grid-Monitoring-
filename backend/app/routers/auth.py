from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import AuditLog, Location, User
from ..schemas import LoginIn, TokenOut, UserOut
from ..security import (
    burn_password_time, clear_login_failures, create_access_token, hash_password, login_locked,
    password_problem, record_login_failure, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

GENERIC_FAIL = "Invalid operator ID, password or location ID."


def _user_out(user: User) -> UserOut:
    return UserOut(operator_id=user.operator_id, full_name=user.full_name, role=user.role, location_code=user.location.code)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    key = body.operator_id.strip().lower()
    if login_locked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again later.")

    user = db.scalars(select(User).where(User.operator_id == body.operator_id.strip())).first()
    loc = db.scalars(select(Location).where(Location.code == body.location_id.strip().upper())).first()
    # Same error and similar timing for every failure mode, so IDs cannot be enumerated.
    if not user:
        burn_password_time(body.password)
    ok = bool(user and user.is_active and verify_password(body.password, user.password_hash) and loc and user.location_id == loc.id)
    if not ok:
        record_login_failure(key)
        db.add(AuditLog(user_id=user.id if user else None, action="LOGIN_FAILED", detail=f"operator={key[:40]}"))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_FAIL)

    clear_login_failures(key)
    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(user_id=user.id, action="LOGIN", detail=""))
    db.commit()
    token, ttl = create_access_token(user.operator_id, user.role, user.token_version)
    return TokenOut(access_token=token, expires_in=ttl, user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Tokens are stateless and short-lived; the client discards its copy. Logged for audit."""
    db.add(AuditLog(user_id=user.id, action="LOGOUT", detail=""))
    db.commit()


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(max_length=128)


@router.post("/change-password", response_model=TokenOut)
def change_password(body: ChangePasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Self-service. Replies 400 (not 401) for a wrong current password so the UI does not sign the user out.
    Every other token the user holds is invalidated; a fresh one is returned for this session."""
    key = "pw:" + user.operator_id.lower()
    if login_locked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again later.")
    if not verify_password(body.current_password, user.password_hash):
        record_login_failure(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    problem = password_problem(body.new_password, user.operator_id)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, problem)
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "New password must differ from the current one")
    clear_login_failures(key)
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.add(AuditLog(user_id=user.id, action="PASSWORD_CHANGE", detail=""))
    db.commit()
    token, ttl = create_access_token(user.operator_id, user.role, user.token_version)
    return TokenOut(access_token=token, expires_in=ttl, user=_user_out(user))
