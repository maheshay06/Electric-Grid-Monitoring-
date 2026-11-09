from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_only, current_user
from ..models import AuditLog, Device, Feeder, User
from ..schemas import DeviceCreatedOut, DeviceCreateIn, DeviceOut
from ..security import generate_device_key, hash_device_key

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut], dependencies=[Depends(current_user)])
def list_devices(db: Session = Depends(get_db)):
    return list(db.scalars(select(Device).order_by(Device.id)))


@router.post("", response_model=DeviceCreatedOut, status_code=201)
def register_device(body: DeviceCreateIn, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    feeder = db.get(Feeder, body.feeder_id)
    if not feeder:
        raise HTTPException(404, "Unknown feeder")
    if feeder.device:
        raise HTTPException(409, "Feeder already has a device; rotate its key instead")
    key = generate_device_key()
    device = Device(feeder_id=feeder.id, name=body.name, api_key_hash=hash_device_key(key))
    feeder.is_installed = True
    feeder.state = "OFFLINE"
    db.add(device)
    db.add(AuditLog(user_id=user.id, action="DEVICE_REGISTER", detail=f"feeder={feeder.id}"))
    db.commit()
    return DeviceCreatedOut.model_validate({**DeviceOut.model_validate(device).model_dump(), "api_key": key})


@router.post("/{device_id}/rotate-key", response_model=DeviceCreatedOut)
def rotate_key(device_id: int, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if not device:
        raise HTTPException(404, "Unknown device")
    key = generate_device_key()
    device.api_key_hash = hash_device_key(key)
    db.add(AuditLog(user_id=user.id, action="DEVICE_KEY_ROTATE", detail=f"device={device_id}"))
    db.commit()
    return DeviceCreatedOut.model_validate({**DeviceOut.model_validate(device).model_dump(), "api_key": key})
