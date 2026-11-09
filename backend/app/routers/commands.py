from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user, operator_or_admin
from ..models import RelayCommand, User
from ..schemas import CommandIn, CommandOut
from ..services import command_service, settings_service

router = APIRouter(prefix="/api/commands", tags=["commands"])


def _out(c: RelayCommand) -> CommandOut:
    out = CommandOut.model_validate(c)
    out.requested_by_name = c.user.operator_id if c.user else None
    return out


@router.post("", response_model=CommandOut, status_code=202)
def create_command(body: CommandIn, user: User = Depends(operator_or_admin), db: Session = Depends(get_db)):
    """Returns 202: the command is only QUEUED. Success is reported later, by device acknowledgement."""
    return _out(command_service.create(db, user, body))


@router.get("", response_model=list[CommandOut], dependencies=[Depends(current_user)])
def list_commands(feeder_id: int | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    q = select(RelayCommand).where(RelayCommand.is_simulated == settings_service.demo_mode(db)).order_by(RelayCommand.id.desc()).limit(limit)
    if feeder_id:
        q = q.where(RelayCommand.feeder_id == feeder_id)
    return [_out(c) for c in db.scalars(q)]


@router.get("/{command_id}", response_model=CommandOut, dependencies=[Depends(current_user)])
def get_command(command_id: int, db: Session = Depends(get_db)):
    cmd = db.get(RelayCommand, command_id)
    if not cmd:
        raise HTTPException(404, "Unknown command")
    return _out(cmd)
