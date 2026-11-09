"""Advisory ML classification.

The model file is produced in Stage 5. Until it exists every function degrades gracefully, and the
API reports `model_available = false` instead of inventing predictions or metrics.

Nothing in this module (or any caller) is allowed to create a RelayCommand.
"""
import json
import logging
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

CLASSES = ["NORMAL", "UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT", "ABNORMAL CONDITION"]
_model = None
_loaded_from: tuple[str, float] | None = None


def _model_path() -> Path:
    return Path(get_settings().ml_model_path)


def model_available() -> bool:
    return _model_path().is_file()


def _load():
    global _model, _loaded_from
    p = _model_path()
    if not p.is_file():
        return None
    stamp = (str(p), p.stat().st_mtime)
    if _model is None or _loaded_from != stamp:
        import joblib  # lazy: keeps the API importable without ML deps

        _model = joblib.load(p)
        _loaded_from = stamp
        log.info("loaded ML model from %s", p)
    return _model


def severity_for(cls: str, voltage: float, nominal: float = 5.0) -> str:
    if cls == "NORMAL":
        return "None"
    if cls == "OVERCURRENT":
        return "High"
    if cls == "ABNORMAL CONDITION":
        return "Medium"
    dev = abs(voltage - nominal) / nominal
    return "High" if dev > 0.15 else "Medium"


def predict(voltage: float, current: float, power: float) -> dict | None:
    """Returns None when no trained model exists."""
    try:
        model = _load()
    except Exception:  # corrupt file / missing deps: never take telemetry ingestion down
        log.exception("ML model failed to load")
        return None
    if model is None:
        return None
    import numpy as np

    x = np.array([[voltage, current, power]])
    proba = model.predict_proba(x)[0]
    idx = int(proba.argmax())
    cls = str(model.classes_[idx])
    return {
        "predicted_class": cls,
        "confidence": float(proba[idx]),
        "severity": severity_for(cls, voltage),
        "model_version": getattr(model, "gm_version", "synthetic-v1"),
    }


def metrics() -> dict:
    p = Path(get_settings().ml_metrics_path)
    if not p.is_file():
        return {"available": False, "synthetic": True, "detail": "Model not trained yet (Stage 5)."}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"available": True, "synthetic": True, **data}
