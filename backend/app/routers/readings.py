from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import SensorReading
from ..schemas import ReadingOut
from ..services import settings_service

router = APIRouter(prefix="/api/readings", tags=["readings"], dependencies=[Depends(current_user)])

RANGE_S = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "24h": 86400}
MAX_POINTS = 300


@router.get("", response_model=list[ReadingOut])
def readings(
    feeder_id: int,
    range: Literal["1m", "5m", "15m", "1h", "24h"] = "5m",
    db: Session = Depends(get_db),
):
    """Live and simulated data are never mixed: Demo Mode selects which one is returned."""
    simulated = settings_service.demo_mode(db)
    since = datetime.now(timezone.utc) - timedelta(seconds=RANGE_S[range])
    rows = list(
        db.scalars(
            select(SensorReading)
            .where(SensorReading.feeder_id == feeder_id, SensorReading.ts >= since, SensorReading.is_simulated == simulated)
            .order_by(SensorReading.ts)
        )
    )
    stride = max(1, -(-len(rows) // MAX_POINTS))
    return rows[::stride]
