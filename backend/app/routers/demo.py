"""Demo-mode controls. Every endpoint is a no-op error unless Demo Mode is on, and none touches hardware."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, operator_or_admin
from ..models import Feeder
from ..schemas import DropAckIn, PushbuttonIn, ScenarioIn
from ..services import demo_simulator, settings_service

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _require_demo(db: Session) -> None:
    if not settings_service.demo_mode(db):
        raise HTTPException(409, "Demo Mode is off")


def _state(db: Session) -> dict:
    return {
        "demo_mode": settings_service.demo_mode(db),
        "drop_ack": demo_simulator.RT.drop_ack,
        "scenarios": {fid: s.scenario for fid, s in demo_simulator.RT.feeders.items()},
    }


@router.get("/state", dependencies=[Depends(current_user)])
def state(db: Session = Depends(get_db)):
    return _state(db)


@router.post("/scenario", dependencies=[Depends(operator_or_admin)])
def scenario(body: ScenarioIn, db: Session = Depends(get_db)):
    _require_demo(db)
    if not db.get(Feeder, body.feeder_id):
        raise HTTPException(404, "Unknown feeder")
    demo_simulator.inject(db, body.feeder_id, body.scenario, body.seconds)
    return _state(db)


@router.post("/drop-ack", dependencies=[Depends(operator_or_admin)])
def drop_ack(body: DropAckIn, db: Session = Depends(get_db)):
    _require_demo(db)
    demo_simulator.RT.drop_ack = body.enabled
    return _state(db)


@router.post("/pushbutton", dependencies=[Depends(operator_or_admin)])
def pushbutton(body: PushbuttonIn, db: Session = Depends(get_db)):
    _require_demo(db)
    feeder = db.get(Feeder, body.feeder_id)
    if not feeder:
        raise HTTPException(404, "Unknown feeder")
    demo_simulator.pushbutton(db, feeder)
    return _state(db)
