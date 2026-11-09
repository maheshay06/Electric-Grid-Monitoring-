#!/usr/bin/env python3
"""Generate a SYNTHETIC, labelled dataset for the fault-classification demo.

*** This data is generated from the operating ranges in config.json. It is NOT measured from
*** hardware and must never be presented as experimental data. A models trained on it can only
*** demonstrate the ML pipeline; its accuracy says nothing about real-world performance.

Classes (Table 7.2 of the project report):
    NORMAL, UNDERVOLTAGE, OVERVOLTAGE, OVERCURRENT, ABNORMAL CONDITION

Labels come from the *clean* sample's operating range. Sensor noise is added afterwards, so samples
near a threshold overlap between classes (as they would with a real ADC) and accuracy is not trivially 100 %.

Usage:
    python generate_dataset.py                          # defaults / config.json
    python generate_dataset.py --samples-per-class 5000 --seed 7 --out data/my.csv
    python generate_dataset.py --config my_ranges.json  # custom operating ranges
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CLASSES = ["NORMAL", "UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT", "ABNORMAL CONDITION"]
DISCLAIMER = "SYNTHETIC DEMO DATA - generated from configured ranges, NOT real hardware measurements."

DEFAULT_CONFIG: dict = {
    "samples_per_class": 2000,
    "seed": 42,
    # Same defaults as the backend rule engine / Settings page (5 V DC prototype).
    "thresholds": {"nominal": 5.0, "undervoltage": 4.5, "overvoltage": 5.5, "overcurrent": 1.5},
    "ranges": {
        "normal": {"voltage": [4.5, 5.5], "voltage_sd": 0.25, "current": [0.0, 1.5]},
        "undervoltage": {"voltage": [3.0, 4.5], "current": [0.0, 1.5]},
        "overvoltage": {"voltage": [5.5, 6.0], "current": [0.0, 1.5]},
        "overcurrent": {"voltage": [4.5, 5.5], "current": [1.5, 4.0]},
        "abnormal": {
            # fractions of the ABNORMAL class made from each unusual pattern (must sum to 1)
            "mix": {"multi_fault": 0.4, "reverse_current": 0.3, "short_circuit_like": 0.3},
            "reverse_current": [-2.0, -0.15],
            "short_circuit_voltage": [0.2, 1.5],
            "short_circuit_current": [0.5, 4.0],
        },
    },
    "sensor_noise": {"voltage": 0.04, "current": 0.05},  # 1-sigma, added after labelling
    "physical": {"max_voltage": 6.0, "max_abs_current": 5.0},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | Path | None = None, **overrides) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    p = Path(path) if path else HERE / "config.json"
    if p.is_file():
        cfg = _merge(cfg, json.loads(p.read_text(encoding="utf-8")))
    return _merge(cfg, {k: v for k, v in overrides.items() if v is not None})


def _uniform(rng, lo_hi, n):
    return rng.uniform(lo_hi[0], lo_hi[1], n)


def _normal_voltage(rng, r, n):
    lo, hi = r["voltage"]
    centre = (lo + hi) / 2
    return np.clip(rng.normal(centre, r["voltage_sd"], n), lo, hi)


def _abnormal(rng, cfg, n):
    a, r = cfg["ranges"]["abnormal"], cfg["ranges"]
    mix = a["mix"]
    if abs(sum(mix.values()) - 1) > 1e-6:
        raise ValueError("ranges.abnormal.mix must sum to 1")
    counts = {k: int(round(n * f)) for k, f in mix.items()}
    counts["multi_fault"] += n - sum(counts.values())  # absorb rounding
    v, i = [], []

    m = counts["multi_fault"]  # out-of-band voltage AND overcurrent at the same time
    low = rng.random(m) < 0.5
    v.append(np.where(low, _uniform(rng, r["undervoltage"]["voltage"], m), _uniform(rng, r["overvoltage"]["voltage"], m)))
    i.append(_uniform(rng, r["overcurrent"]["current"], m))

    m = counts["reverse_current"]  # normal voltage, current flowing the wrong way
    v.append(_normal_voltage(rng, r["normal"], m))
    i.append(_uniform(rng, a["reverse_current"], m))

    m = counts["short_circuit_like"]  # collapsed voltage with heavy current
    v.append(_uniform(rng, a["short_circuit_voltage"], m))
    i.append(_uniform(rng, a["short_circuit_current"], m))
    return np.concatenate(v), np.concatenate(i)


def generate(cfg: dict) -> pd.DataFrame:
    rng = np.random.default_rng(cfg["seed"])
    n = int(cfg["samples_per_class"])
    r = cfg["ranges"]
    parts = {}

    parts["NORMAL"] = (_normal_voltage(rng, r["normal"], n), _uniform(rng, r["normal"]["current"], n))
    parts["UNDERVOLTAGE"] = (_uniform(rng, r["undervoltage"]["voltage"], n), _uniform(rng, r["undervoltage"]["current"], n))
    parts["OVERVOLTAGE"] = (_uniform(rng, r["overvoltage"]["voltage"], n), _uniform(rng, r["overvoltage"]["current"], n))
    parts["OVERCURRENT"] = (_uniform(rng, r["overcurrent"]["voltage"], n), _uniform(rng, r["overcurrent"]["current"], n))
    parts["ABNORMAL CONDITION"] = _abnormal(rng, cfg, n)

    frames = []
    ph, nz = cfg["physical"], cfg["sensor_noise"]
    for label in CLASSES:
        v, i = parts[label]
        v = np.clip(v + rng.normal(0, nz["voltage"], len(v)), 0, ph["max_voltage"])
        i = np.clip(i + rng.normal(0, nz["current"], len(i)), -ph["max_abs_current"], ph["max_abs_current"])
        frames.append(pd.DataFrame({"voltage": v, "current": i, "power": v * i, "label": label}))
    df = pd.concat(frames, ignore_index=True).sample(frac=1, random_state=cfg["seed"]).reset_index(drop=True)
    df[["voltage", "current", "power"]] = df[["voltage", "current", "power"]].round(4)
    df["data_source"] = "SYNTHETIC"
    return df


def write(df: pd.DataFrame, cfg: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    meta = {
        "disclaimer": DISCLAIMER,
        "synthetic": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(len(df)),
        "class_counts": df["label"].value_counts().to_dict(),
        "config": cfg,
    }
    meta_path = out.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON file overriding the default operating ranges")
    ap.add_argument("--samples-per-class", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--noise-voltage", type=float, help="sensor noise sigma (V)")
    ap.add_argument("--noise-current", type=float, help="sensor noise sigma (A)")
    ap.add_argument("--out", default=str(HERE / "data" / "synthetic_dataset.csv"))
    a = ap.parse_args()

    noise = {}
    if a.noise_voltage is not None:
        noise["voltage"] = a.noise_voltage
    if a.noise_current is not None:
        noise["current"] = a.noise_current
    cfg = load_config(a.config, samples_per_class=a.samples_per_class, seed=a.seed, sensor_noise=noise or None)

    df = generate(cfg)
    meta = write(df, cfg, Path(a.out))
    print(DISCLAIMER)
    print(f"Wrote {len(df)} rows -> {a.out}\nMetadata -> {meta}")
    print(df["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
