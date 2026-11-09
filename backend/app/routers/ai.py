from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import AIPrediction
from ..schemas import PredictIn, PredictionOut
from ..services import ai_service, settings_service

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(current_user)])

# Every endpoint here is read-only with respect to hardware: there is deliberately no import of
# command_service in this module.


@router.post("/predict", response_model=PredictionOut)
def predict(body: PredictIn):
    power = body.power if body.power is not None else body.voltage * body.current
    result = ai_service.predict(body.voltage, body.current, power)
    if result is None:
        raise HTTPException(503, "ML model not available yet (train it in Stage 5).")
    return PredictionOut(voltage=body.voltage, current=body.current, power=power, **result)


@router.get("/latest", response_model=PredictionOut | None)
def latest(feeder_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(AIPrediction).where(AIPrediction.feeder_id == feeder_id, AIPrediction.is_simulated_input == settings_service.demo_mode(db))
        .order_by(AIPrediction.id.desc()).limit(1)
    ).first()


@router.get("/history", response_model=list[PredictionOut])
def history(feeder_id: int, limit: int = Query(50, ge=1, le=300), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(AIPrediction)
            .where(AIPrediction.feeder_id == feeder_id, AIPrediction.is_simulated_input == settings_service.demo_mode(db))
            .order_by(AIPrediction.id.desc()).limit(limit)
        )
    )


@router.get("/metrics")
def metrics():
    return {"model_available": ai_service.model_available(), **ai_service.metrics()}
