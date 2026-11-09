"""Admin user management. Users are never hard-deleted (audit rows and command history reference them);
they are deactivated, which also blocks every token they hold."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, validator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_only
from ..models import AuditLog, Location, User
from ..security import hash_password, password_problem

router = APIRouter(prefix="/api/users", tags=["users"])

OPERATOR_ID = re.compile(r"^[A-Za-z0-9_.\-]{3,64}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
Role = Literal["admin", "operator", "viewer"]


def _email(v: str | None) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if len(v) > 160 or not EMAIL.match(v):
        raise ValueError("invalid email address")
    return v.lower()


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: str
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    role: Role = "operator"
    location_code: str = Field(min_length=1, max_length=32)
    password: str = Field(max_length=128)

    @validator("operator_id")
    def _oid(cls, v: str) -> str:
        v = v.strip()
        if not OPERATOR_ID.match(v):
            raise ValueError("operator ID must be 3-64 characters: letters, digits, . _ -")
        return v


    @validator("email")
    def _em(cls, v):
        return _email(v)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    location_code: str | None = Field(default=None, min_length=1, max_length=32)

    @validator("email")
    def _em(cls, v):
        return _email(v)


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_password: str = Field(max_length=128)


def _out(u: User) -> dict:
    return {
        "id": u.id, "operator_id": u.operator_id, "full_name": u.full_name, "email": u.email, "role": u.role,
        "location_code": u.location.code, "is_active": u.is_active,
        "created_at": u.created_at.isoformat(), "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


def _location(db: Session, code: str) -> Location:
    loc = db.scalars(select(Location).where(Location.code == code.strip().upper())).first()
    if not loc:
        raise HTTPException(422, f"Unknown location {code!r}")
    return loc


@router.get("")
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [_out(u) for u in db.scalars(select(User).order_by(User.id))]


@router.get("/locations")
def locations(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [{"code": loc.code, "name": loc.name} for loc in db.scalars(select(Location).order_by(Location.id))]


@router.post("", status_code=201)
def create_user(body: UserCreate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.operator_id) == body.operator_id.lower())):
        raise HTTPException(409, "That operator ID is already taken")
    if body.email and db.scalars(select(User).where(User.email == body.email)).first():
        raise HTTPException(409, "That email is already in use")
    problem = password_problem(body.password, body.operator_id)
    if problem:
        raise HTTPException(422, problem)
    u = User(operator_id=body.operator_id, full_name=body.full_name.strip(), email=body.email, role=body.role,
             location_id=_location(db, body.location_code).id, password_hash=hash_password(body.password))
    db.add(u)
    db.add(AuditLog(user_id=admin.id, action="USER_CREATE", detail=f"{u.operator_id} role={u.role}"))
    db.commit()
    return _out(u)


@router.patch("/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Unknown user")
    changes = body.model_dump(exclude_unset=True)
    if u.id == admin.id and (changes.get("role", u.role) != "admin" or changes.get("is_active", True) is False):
        # Also guarantees at least one active admin always remains: the acting admin.
        raise HTTPException(409, "You cannot demote or deactivate your own account")
    if "email" in changes and changes["email"] and changes["email"] != u.email:
        if db.scalars(select(User).where(User.email == changes["email"])).first():
            raise HTTPException(409, "That email is already in use")
    if "location_code" in changes:
        u.location_id = _location(db, changes.pop("location_code")).id
    for k, v in changes.items():
        setattr(u, k, v)
    if "role" in changes or "is_active" in changes:
        u.token_version += 1  # sign the user out everywhere so the change is felt immediately
    db.add(AuditLog(user_id=admin.id, action="USER_UPDATE",
                    detail=f"{u.operator_id} {sorted(body.model_dump(exclude_unset=True))}"[:400]))
    db.commit()
    return _out(u)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: int, body: ResetPasswordIn, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Unknown user")
    problem = password_problem(body.new_password, u.operator_id)
    if problem:
        raise HTTPException(422, problem)
    u.password_hash = hash_password(body.new_password)
    u.token_version += 1  # every token the user already holds stops working
    db.add(AuditLog(user_id=admin.id, action="USER_PASSWORD_RESET", detail=u.operator_id))
    db.commit()