from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import admin_only, current_user
from ..models import AuditLog, User
from ..schemas import SettingsIn, SettingsOut
from ..services import demo_simulator, settings_service
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _out(db: Session) -> SettingsOut:
    s = get_settings()
    return SettingsOut(
        demo_mode=settings_service.demo_mode(db),
        heartbeat_timeout_s=s.heartbeat_timeout_s,
        command_timeout_s=s.command_timeout_s,
    )


@router.get("", response_model=SettingsOut, dependencies=[Depends(current_user)])
def read_settings(db: Session = Depends(get_db)):
    return _out(db)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    was = settings_service.demo_mode(db)
    settings_service.put(db, "demo_mode", "true" if body.demo_mode else "false")
    db.add(AuditLog(user_id=user.id, action="DEMO_MODE", detail=str(body.demo_mode)))
    db.commit()
    if body.demo_mode and not was:
        demo_simulator.enable(db)  # fresh simulated run + 24 h backfill, clearly flagged is_simulated
    ws_manager.publish("settings")
    return _out(db)
