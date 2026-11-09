from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, operator_or_admin
from ..models import AuditLog, FaultEvent, User
from ..schemas import FaultOut, FaultPage
from ..services import settings_service
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/api/faults", tags=["faults"])


@router.get("", response_model=FaultPage, dependencies=[Depends(current_user)])
def list_faults(
    feeder_id: int | None = None,
    type: str | None = Query(default=None, max_length=24),
    status: str | None = Query(default=None, pattern="^(ACTIVE|ACKNOWLEDGED|CLEARED)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = select(FaultEvent).where(FaultEvent.is_simulated == settings_service.demo_mode(db))
    if feeder_id:
        q = q.where(FaultEvent.feeder_id == feeder_id)
    if type:
        q = q.where(FaultEvent.type == type)
    if status:
        q = q.where(FaultEvent.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(db.scalars(q.order_by(FaultEvent.ts.desc()).offset(skip).limit(limit)))
    return FaultPage(total=total, items=items)


@router.post("/{fault_id}/acknowledge", response_model=FaultOut)
def acknowledge(fault_id: int, user: User = Depends(operator_or_admin), db: Session = Depends(get_db)):
    ev = db.get(FaultEvent, fault_id)
    if not ev:
        raise HTTPException(404, "Unknown event")
    if ev.status == "ACTIVE":
        ev.status = "ACKNOWLEDGED"
        db.add(AuditLog(user_id=user.id, action="FAULT_ACK", detail=f"event={fault_id}"))
        db.commit()
        ws_manager.publish("fault", feeder_id=ev.feeder_id)
    return ev
