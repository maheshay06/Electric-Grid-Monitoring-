import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import SmsMessage
from . import sms_service, twilio_client
from .twilio_client import TwilioError

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def process_queue(db: Session) -> int:
    """Sends due QUEUED messages. Returns how many were handed to Twilio."""
    now = datetime.now(timezone.utc)
    due = list(
        db.scalars(
            select(SmsMessage).where(SmsMessage.status == "QUEUED")
            .where((SmsMessage.next_attempt_at.is_(None)) | (SmsMessage.next_attempt_at <= now))
            .order_by(SmsMessage.id).limit(20)
        )
    )
    sent = 0
    max_age = timedelta(seconds=get_settings().sms_max_age_s)
    for m in due:
        if not sms_service.is_enabled(db) and not m.is_test:
            m.status, m.error = "SKIPPED", "SMS alerts disabled before sending"
            continue
        if now - m.created_at > max_age:  # an hours-old "overcurrent now" text is worse than none
            m.status, m.error = "SKIPPED", "stale: not sent (older than max age)"
            continue
        try:
            res = twilio_client.send_sms(m.to_number, m.body)
            m.status, m.twilio_sid, m.sent_at, m.error = "SENT", res["sid"], now, None
            m.attempts += 1
            sent += 1
        except TwilioError as e:
            m.attempts += 1
            m.error = str(e)[:200]
            if e.permanent or m.attempts >= MAX_ATTEMPTS:
                m.status = "FAILED"
                log.warning("SMS %s to %s failed: %s", m.id, sms_service.mask(m.to_number), m.error)
            else:
                m.next_attempt_at = now + timedelta(seconds=5 * 2 ** m.attempts)
    if due:
        db.commit()
    return sent


async def run_forever() -> None:
    while True:
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(process_queue, db)
        except Exception:
            log.exception("sms worker pass failed")
        await asyncio.sleep(2)
