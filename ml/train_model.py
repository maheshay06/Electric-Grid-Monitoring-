#!/usr/bin/env python3
"""Train the fault classifier on the SYNTHETIC dataset and write the model + metrics.

Outputs (read by the backend):
    models/fault_classifier.joblib   the fitted estimator (exposes predict_proba / classes_)
    models/metrics.json              hold-out metrics on SYNTHETIC test data only

Usage:
    python train_model.py                      # Random Forest (default)
    python train_model.py --algorithm dt       # Decision Tree
    python train_model.py --algorithm knn      # K-Nearest Neighbours (standardised features)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

HERE = Path(__file__).resolve().parent
FEATURES = ["voltage", "current", "power"]  # must match backend/app/services/ai_service.py
CLASSES = ["NORMAL", "UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT", "ABNORMAL CONDITION"]
DISCLAIMER = (
    "Trained and evaluated on SYNTHETIC demo data only. These figures describe performance on generated "
    "samples, not on real hardware measurements, and must not be quoted as real-world accuracy."
)


def build_model(algorithm: str, seed: int):
    if algorithm == "rf":
        return RandomForestClassifier(n_estimators=200, min_samples_leaf=2, class_weight="balanced", random_state=seed, n_jobs=-1)
    if algorithm == "dt":
        return DecisionTreeClassifier(max_depth=10, class_weight="balanced", random_state=seed)
    if algorithm == "knn":
        return make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=7, weights="distance"))
    raise ValueError(f"unknown algorithm {algorithm!r}")


def train(df: pd.DataFrame, out_dir: Path, algorithm: str = "rf", seed: int = 42, test_size: float = 0.2, meta: dict | None = None) -> dict:
    if "data_source" in df and not (df["data_source"] == "SYNTHETIC").all():
        raise SystemExit("Refusing to train: dataset contains rows not marked SYNTHETIC.")
    unknown = set(df["label"]) - set(CLASSES)
    if unknown:
        raise SystemExit(f"Unknown labels in dataset: {sorted(unknown)}")

    X, y = df[FEATURES].to_numpy(), df["label"].to_numpy()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=test_size, stratify=y, random_state=seed)

    model = build_model(algorithm, seed)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)

    labels = [c for c in CLASSES if c in set(y)]
    p, r, f, s = precision_recall_fscore_support(y_te, pred, labels=labels, zero_division=0)
    cv = cross_val_score(build_model(algorithm, seed), X_tr, y_tr, cv=StratifiedKFold(5, shuffle=True, random_state=seed), scoring="accuracy")

    model.gm_version = f"synthetic-{algorithm}-v1"
    metrics = {
        "model_version": model.gm_version,
        "algorithm": {"rf": "Random Forest", "dt": "Decision Tree", "knn": "K-Nearest Neighbours"}[algorithm],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "sklearn_version": sklearn.__version__,
        "features": FEATURES,
        "train_samples": int(len(y_tr)),
        "test_samples": int(len(y_te)),
        "accuracy": float(accuracy_score(y_te, pred)),
        "macro_f1": float(f1_score(y_te, pred, labels=labels, average="macro", zero_division=0)),
        "cv_accuracy_mean": float(cv.mean()),
        "cv_accuracy_std": float(cv.std()),
        "per_class": {
            c: {"precision": float(p[k]), "recall": float(r[k]), "f1": float(f[k]), "support": int(s[k])}
            for k, c in enumerate(labels)
        },
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_te, pred, labels=labels).tolist()},
        "disclaimer": DISCLAIMER,
    }
    if hasattr(model, "feature_importances_"):
        metrics["feature_importance"] = dict(zip(FEATURES, map(float, model.feature_importances_)))
    if meta:
        metrics["dataset"] = {k: meta[k] for k in ("generated_at", "rows", "class_counts") if k in meta}

    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_dir / "fault_classifier.joblib")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(HERE / "data" / "synthetic_dataset.csv"))
    ap.add_argument("--out-dir", default=str(HERE / "models"))
    ap.add_argument("--algorithm", choices=["rf", "dt", "knn"], default="rf")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    data = Path(a.data)
    if not data.is_file():
        raise SystemExit(f"{data} not found. Run generate_dataset.py first.")
    meta_path = data.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else None

    m = train(pd.read_csv(data), Path(a.out_dir), a.algorithm, a.seed, meta=meta)
    print(DISCLAIMER)
    print(f"{m['algorithm']}: accuracy={m['accuracy']:.4f}  macro-F1={m['macro_f1']:.4f}  "
          f"5-fold CV={m['cv_accuracy_mean']:.4f}+/-{m['cv_accuracy_std']:.4f}  (n_test={m['test_samples']})")
    for c, v in m["per_class"].items():
        print(f"  {c:<20} P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f} n={v['support']}")
    print(f"Saved model + metrics to {a.out_dir}")


if __name__ == "__main__":
    main()
