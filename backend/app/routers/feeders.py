from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_only, current_user
from ..models import AuditLog, Feeder, User
from ..schemas import FeederOut, ThresholdsIn
from ..services.feeder_view import feeder_out

router = APIRouter(prefix="/api/feeders", tags=["feeders"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[FeederOut])
def list_feeders(db: Session = Depends(get_db)):
    return [feeder_out(db, f) for f in db.scalars(select(Feeder).order_by(Feeder.number))]


@router.get("/{feeder_id}", response_model=FeederOut)
def get_feeder(feeder_id: int, db: Session = Depends(get_db)):
    feeder = db.get(Feeder, feeder_id)
    if not feeder:
        raise HTTPException(404, "Unknown feeder")
    return feeder_out(db, feeder)


@router.put("/{feeder_id}/thresholds", response_model=FeederOut)
def set_thresholds(feeder_id: int, body: ThresholdsIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    feeder = db.get(Feeder, feeder_id)
    if not feeder:
        raise HTTPException(404, "Unknown feeder")
    for k, v in body.model_dump().items():
        setattr(feeder, k, v)
    db.add(AuditLog(user_id=user.id, action="THRESHOLDS", detail=f"feeder={feeder_id} {body.model_dump()}"[:400]))
    db.commit()
    return feeder_out(db, feeder)
