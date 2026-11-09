from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, validator

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import admin_only, current_user
from ..models import AuditLog, Feeder, SmsMessage, SmsRecipient, User
from ..services import settings_service, sms_service

router = APIRouter(prefix="/api/sms", tags=["sms"])


class RecipientIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone: str = Field(description="E.164, e.g. +919876543210")
    label: str = Field(default="", max_length=60)

    @validator("phone")
    def _e164(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not sms_service.E164.match(v):
            raise ValueError("phone must be in E.164 format, e.g. +919876543210")
        return v


class EnabledIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class TestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient_id: int


@router.get("/status", dependencies=[Depends(current_user)])
def status(db: Session = Depends(get_db)):
    s = get_settings()
    n = len(list(db.scalars(select(SmsRecipient).where(SmsRecipient.is_active.is_(True)))))
    return {
        "configured": s.sms_configured,
        "enabled": sms_service.is_enabled(db),
        "sender": sms_service.mask(s.twilio_from_number) if s.twilio_from_number else ("messaging service" if s.twilio_messaging_service_sid else None),
        "active_recipients": n,
        "repeat_interval_s": s.sms_repeat_interval_s,
        "state_change_interval_s": s.sms_state_change_interval_s,
        "demo_mode_never_sends": True,
        "note": "SENT means Twilio accepted the message; delivery receipts are not tracked.",
    }


@router.put("/enabled")
def set_enabled(body: EnabledIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if body.enabled and not get_settings().sms_configured:
        raise HTTPException(409, "Twilio is not configured (set TWILIO_* variables in backend/.env)")
    settings_service.put(db, "sms_enabled", "true" if body.enabled else "false")
    db.add(AuditLog(user_id=user.id, action="SMS_ENABLED", detail=str(body.enabled)))
    db.commit()
    return {"enabled": sms_service.is_enabled(db)}


@router.get("/recipients")
def list_recipients(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return [
        {"id": r.id, "phone": r.phone, "label": r.label, "is_active": r.is_active}
        for r in db.scalars(select(SmsRecipient).order_by(SmsRecipient.id))
    ]


@router.post("/recipients", status_code=201)
def add_recipient(body: RecipientIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalars(select(SmsRecipient).where(SmsRecipient.phone == body.phone)).first():
        raise HTTPException(409, "Recipient already exists")
    r = SmsRecipient(phone=body.phone, label=body.label.strip())
    db.add(r)
    db.add(AuditLog(user_id=user.id, action="SMS_RECIPIENT_ADD", detail=sms_service.mask(body.phone)))
    db.commit()
    return {"id": r.id, "phone": r.phone, "label": r.label, "is_active": r.is_active}


@router.delete("/recipients/{recipient_id}", status_code=204)
def delete_recipient(recipient_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = db.get(SmsRecipient, recipient_id)
    if not r:
        raise HTTPException(404, "Unknown recipient")
    db.add(AuditLog(user_id=user.id, action="SMS_RECIPIENT_DELETE", detail=sms_service.mask(r.phone)))
    db.delete(r)
    db.commit()
    return None


@router.post("/test", status_code=202)
def send_test(body: TestIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Sends one real SMS (billed by Twilio) to ONE chosen recipient. Needs credentials, not the alert switch."""
    if not get_settings().sms_configured:
        raise HTTPException(409, "Twilio is not configured")
    r = db.get(SmsRecipient, body.recipient_id)
    if not r:
        raise HTTPException(404, "Unknown recipient")
    feeder = db.scalars(select(Feeder).order_by(Feeder.number)).first()
    n = sms_service.enqueue(db, "TEST", feeder, force=True, only_recipient_id=r.id)
    db.add(AuditLog(user_id=user.id, action="SMS_TEST", detail=sms_service.mask(r.phone)))
    db.commit()
    return {"queued": n}


@router.get("/messages", dependencies=[Depends(current_user)])
def messages(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)):
    rows = db.scalars(select(SmsMessage).order_by(SmsMessage.id.desc()).limit(limit))
    return [
        {
            "id": m.id, "created_at": m.created_at.isoformat(), "kind": m.kind, "feeder_id": m.feeder_id,
            "to": sms_service.mask(m.to_number), "status": m.status, "attempts": m.attempts, "error": m.error,
            "sent_at": m.sent_at.isoformat() if m.sent_at else None, "body": m.body,
        }
        for m in rows
    ]