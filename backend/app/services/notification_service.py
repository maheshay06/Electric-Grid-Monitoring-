from sqlalchemy.orm import Session

from ..models import Notification
from .ws_manager import ws_manager


def notify(
    db: Session,
    *,
    kind: str,
    severity: str,
    title: str,
    message: str,
    feeder_id: int | None = None,
    event_id: int | None = None,
    is_simulated: bool = False,
) -> Notification:
    """Adds a broadcast in-app notification to the session (caller commits, then calls publish)."""
    n = Notification(
        kind=kind, severity=severity, title=title[:160], message=message[:400],
        feeder_id=feeder_id, related_event_id=event_id, is_simulated=is_simulated,
    )
    db.add(n)
    return n


def announce() -> None:
    ws_manager.publish("notification")
