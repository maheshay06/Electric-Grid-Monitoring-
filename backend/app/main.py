import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (register tables)
from .config import get_settings
from .database import Base, engine
from .migrate import add_missing_columns
from .routers import ai, auth, commands, dashboard, demo, device_api, devices, faults, feeders, notifications, readings, settings, sms, users, ws
from .services import demo_simulator, heartbeat_monitor, sms_worker
from .services.ws_manager import ws_manager

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    add_missing_columns(engine)  # upgrades databases created by older versions
    ws_manager.bind_loop(asyncio.get_running_loop())
    tasks = []
    if get_settings().enable_background_tasks:
        tasks = [asyncio.create_task(heartbeat_monitor.run_forever()), asyncio.create_task(demo_simulator.run_forever()),
                 asyncio.create_task(sms_worker.run_forever())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(
    title="ESP32 Grid Monitoring & Control API",
    version="0.1.0",
    description="Feeder monitoring, acknowledged relay control and advisory ML fault classification.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)

for r in (auth, dashboard, feeders, readings, faults, ai, commands, notifications, devices, settings, sms, users, device_api, demo, ws):
    app.include_router(r.router)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}
