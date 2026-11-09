#!/usr/bin/env python3
"""Classify one reading from the command line (advisory output only).

    python predict.py --voltage 4.1 --current 0.4
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np

HERE = Path(__file__).resolve().parent


def severity_for(cls: str, voltage: float, nominal: float = 5.0) -> str:
    # Keep identical to backend/app/services/ai_service.py
    if cls == "NORMAL":
        return "None"
    if cls == "OVERCURRENT":
        return "High"
    if cls == "ABNORMAL CONDITION":
        return "Medium"
    return "High" if abs(voltage - nominal) / nominal > 0.15 else "Medium"


def predict(model, voltage: float, current: float, power: float | None = None) -> dict:
    power = voltage * current if power is None else power
    proba = model.predict_proba(np.array([[voltage, current, power]]))[0]
    k = int(proba.argmax())
    cls = str(model.classes_[k])
    return {
        "predicted_class": cls,
        "confidence": round(float(proba[k]), 4),
        "severity": severity_for(cls, voltage),
        "probabilities": {str(c): round(float(p), 4) for c, p in zip(model.classes_, proba)},
        "advisory_only": True,
        "synthetic_model": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voltage", type=float, required=True)
    ap.add_argument("--current", type=float, required=True)
    ap.add_argument("--power", type=float)
    ap.add_argument("--model", default=str(HERE / "models" / "fault_classifier.joblib"))
    a = ap.parse_args()
    if not Path(a.model).is_file():
        raise SystemExit("No trained model. Run generate_dataset.py then train_model.py.")
    print(json.dumps(predict(joblib.load(a.model), a.voltage, a.current, a.power), indent=2))


if __name__ == "__main__":
    main()
