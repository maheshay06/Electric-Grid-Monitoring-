from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import Notification, User
from ..schemas import NotificationOut
from ..services import settings_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _visible(user: User, demo: bool):
    return (Notification.is_simulated == demo) & or_(Notification.user_id.is_(None), Notification.user_id == user.id)


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False, limit: int = Query(100, ge=1, le=300),
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    q = select(Notification).where(_visible(user, settings_service.demo_mode(db)))
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    return list(db.scalars(q.order_by(Notification.created_at.desc()).limit(limit)))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if not n or (n.user_id not in (None, user.id)):
        raise HTTPException(404, "Unknown notification")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return n


@router.post("/read-all", status_code=204)
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(_visible(user, settings_service.demo_mode(db)), Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()
