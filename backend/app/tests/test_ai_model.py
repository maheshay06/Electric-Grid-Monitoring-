"""Backend <-> trained model integration. Skipped where scikit-learn cannot be imported."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")

from app.database import SessionLocal  # noqa: E402
from app.models import AIPrediction, RelayCommand  # noqa: E402
from app.services import ai_service  # noqa: E402

from .conftest import send_telemetry  # noqa: E402

ML_DIR = Path(__file__).resolve().parents[3] / "ml"


@pytest.fixture()
def trained(tmp_path, monkeypatch):
    sys.path.insert(0, str(ML_DIR))
    import generate_dataset as gd
    import train_model as tm

    tm.train(gd.generate(gd.load_config(samples_per_class=300, seed=3)), tmp_path, "rf", seed=3)
    monkeypatch.setattr(ai_service, "_model_path", lambda: tmp_path / "fault_classifier.joblib")
    monkeypatch.setattr(ai_service, "_model", None)
    monkeypatch.setattr(ai_service, "_loaded_from", None)

    class S:  # minimal stand-in so metrics() reads the temp file
        ml_metrics_path = str(tmp_path / "metrics.json")

    monkeypatch.setattr(ai_service, "get_settings", lambda: S)
    yield tmp_path


def test_predict_endpoint_uses_trained_model(client, op_h, trained):
    r = client.post("/api/ai/predict", headers=op_h, json={"voltage": 4.0, "current": 0.4})
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_class"] == "UNDERVOLTAGE"
    assert 0 < body["confidence"] <= 1 and body["advisory_only"] and body["is_synthetic_model"]


def test_metrics_endpoint_flags_synthetic(client, op_h, trained):
    m = client.get("/api/ai/metrics", headers=op_h).json()
    assert m["model_available"] and m["synthetic"] is True and "SYNTHETIC" in m["disclaimer"]


def test_telemetry_stores_prediction_but_issues_no_command(client, dev_h, op_h, trained):
    with SessionLocal() as db:
        cmds = db.query(RelayCommand).count()
        preds = db.query(AIPrediction).count()
    assert send_telemetry(client, dev_h, v=5.0, i=2.4, relay="ENERGISED").status_code == 202
    with SessionLocal() as db:
        assert db.query(AIPrediction).count() == preds + 1
        last = db.query(AIPrediction).order_by(AIPrediction.id.desc()).first()
        assert last.predicted_class == "OVERCURRENT" and last.advisory_only and last.is_synthetic_model
        assert db.query(RelayCommand).count() == cmds        # a bad prediction never creates a command
    f1 = next(f for f in client.get("/api/feeders", headers=op_h).json() if f["number"] == 1)
    assert f1["state"] == "NORMAL"
