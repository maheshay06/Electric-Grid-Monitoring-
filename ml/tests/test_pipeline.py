import sys
from pathlib import Path

import joblib
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_dataset as gd  # noqa: E402
import predict as pr  # noqa: E402
import train_model as tm  # noqa: E402


@pytest.fixture(scope="module")
def df():
    return gd.generate(gd.load_config(samples_per_class=400, seed=1))


def test_dataset_is_balanced_labelled_and_marked_synthetic(df):
    assert set(df["label"]) == set(gd.CLASSES)
    assert (df["label"].value_counts() == 400).all()
    assert (df["data_source"] == "SYNTHETIC").all()
    assert df["voltage"].between(0, 6).all() and df["current"].abs().le(5).all()
    assert ((df["voltage"] * df["current"] - df["power"]).abs() < 1e-3).all()


def test_class_ranges_follow_configured_thresholds(df):
    g = df.groupby("label")
    assert g["voltage"].mean()["UNDERVOLTAGE"] < 4.5 < g["voltage"].mean()["NORMAL"] < 5.5 < g["voltage"].mean()["OVERVOLTAGE"]
    assert g["current"].mean()["OVERCURRENT"] > 1.5
    assert (df[df.label == "ABNORMAL CONDITION"]["current"] < 0).mean() > 0.2   # reverse-current pattern present


def test_generation_is_reproducible_and_configurable():
    a = gd.generate(gd.load_config(samples_per_class=50, seed=9))
    b = gd.generate(gd.load_config(samples_per_class=50, seed=9))
    c = gd.generate(gd.load_config(samples_per_class=50, seed=10))
    assert a.equals(b) and not a.equals(c)
    narrow = gd.load_config(samples_per_class=50, seed=9, thresholds={"nominal": 12.0})
    assert narrow["thresholds"]["nominal"] == 12.0


def test_training_writes_model_and_honest_metrics(df, tmp_path):
    m = tm.train(df, tmp_path, "rf", seed=1)
    assert (tmp_path / "fault_classifier.joblib").is_file() and (tmp_path / "metrics.json").is_file()
    assert 0.8 < m["accuracy"] < 1.0                      # strong but not a suspicious 100 %
    assert set(m["per_class"]) == set(gd.CLASSES)
    assert "SYNTHETIC" in m["disclaimer"]
    model = joblib.load(tmp_path / "fault_classifier.joblib")
    assert pr.predict(model, 5.0, 0.4)["predicted_class"] == "NORMAL"
    assert pr.predict(model, 4.0, 0.4)["predicted_class"] == "UNDERVOLTAGE"
    assert pr.predict(model, 5.9, 0.4)["predicted_class"] == "OVERVOLTAGE"
    assert pr.predict(model, 5.0, 2.5)["predicted_class"] == "OVERCURRENT"
    assert pr.predict(model, 5.0, -1.0)["advisory_only"] is True


def test_refuses_non_synthetic_data(df, tmp_path):
    bad = df.copy()
    bad.loc[0, "data_source"] = "MEASURED"
    with pytest.raises(SystemExit):
        tm.train(bad, tmp_path)
