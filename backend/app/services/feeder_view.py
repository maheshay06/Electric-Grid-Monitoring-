"""Feeder presentation: real DB state when live, in-memory simulated state when Demo Mode is on."""
from sqlalchemy.orm import Session

from ..models import Feeder
from ..schemas import FeederOut
from . import demo_simulator, settings_service


def feeder_out(db: Session, f: Feeder, demo: bool | None = None) -> FeederOut:
    demo = settings_service.demo_mode(db) if demo is None else demo
    out = FeederOut.model_validate(f)
    if demo:
        st = demo_simulator.state_for(f.id).state
        relay, load = demo_simulator.relay_and_load(st)
        out.is_installed, out.state, out.relay_state, out.load_state, out.simulated = True, st, relay, load, True
    return out
