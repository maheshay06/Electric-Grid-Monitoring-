from sqlalchemy.orm import Session

from ..models import SystemSetting


def get(db: Session, key: str, default: str) -> str:
    row = db.get(SystemSetting, key)
    return row.value if row else default


def put(db: Session, key: str, value: str) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))


def demo_mode(db: Session) -> bool:
    return get(db, "demo_mode", "false") == "true"
