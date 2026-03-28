"""
train.py — One-shot training script for the Mars Rover anomaly detection ensemble.

NASA REMS real data ranges:
    temperature  : -90 … +30 °C (normal)  | >40 or <-110 (anomaly)
    radiation    :  180 … 280 μSv/h (normal) | >500 (solar flare anomaly)
    methane_level:  0.3 … 0.7 ppb (normal) | >1.5 ppb (anomaly)

Run ONCE before starting the server:
    python train.py

Produces:
    models/ensemble.joblib  — serialised {if_model, lof_model, zscore_stats}
"""

import io
import os
import sys

import numpy as np
import joblib

# Force UTF-8 output on Windows (avoids UnicodeEncodeError with Turkish/emoji chars)
if sys.stdout.encoding and sys.stdout.encoding.upper() not in ("UTF-8", "UTF8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

# ── Output directory ────────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODELS_DIR, "ensemble.joblib")

# ── NASA REMS real data ranges ───────────────────────────────────────────────────
#   temperature  : -90 … +30  °C    (normal)  | >40 or <-110  (anomaly)
#   radiation    :  180 … 280 μSv/h (normal)  | >500           (anomaly — solar flare)
#   methane_level:  0.3 … 0.7 ppb  (normal)  | >1.5 ppb       (anomaly)

RANDOM_STATE = 42
N_NORMAL = 9_000
N_ANOMALY = 1_000   # ~10 % contamination — matches IsolationForest/LOF setting

rng = np.random.default_rng(RANDOM_STATE)

# ── Anomaly thresholds (used in self-test) ───────────────────────────────────────
TEMP_MIN_NORMAL  = -90.0
TEMP_MAX_NORMAL  =  30.0
TEMP_ANOMALY_HI  =  45.0   # >40 → use 45 to be clearly anomalous
TEMP_ANOMALY_LO  = -115.0  # <-110 → use -115

RAD_MIN_NORMAL   = 180.0
RAD_MAX_NORMAL   = 280.0
RAD_ANOMALY      = 550.0   # >500 μSv/h

METH_MIN_NORMAL  = 0.3
METH_MAX_NORMAL  = 0.7
METH_ANOMALY     = 2.0     # >1.5 ppb


def generate_normal_samples(n: int) -> np.ndarray:
    """Draw samples from the nominal NASA REMS Mars operating envelope."""
    temperature    = rng.uniform(TEMP_MIN_NORMAL, TEMP_MAX_NORMAL, n)
    methane_level  = rng.uniform(METH_MIN_NORMAL, METH_MAX_NORMAL, n)
    radiation      = rng.uniform(RAD_MIN_NORMAL,  RAD_MAX_NORMAL,  n)
    return np.column_stack([temperature, methane_level, radiation])


def generate_anomaly_samples(n: int) -> np.ndarray:
    """Draw samples from anomalous regions (beyond NASA REMS safe thresholds)."""
    n_temp  = n // 3
    n_meth  = n // 3
    n_rad   = n - n_temp - n_meth

    # Temperature anomalies: >40 or <-110
    temp_high = rng.uniform(41.0, 120.0, n_temp // 2)
    temp_low  = rng.uniform(-150.0, -111.0, n_temp - n_temp // 2)
    temp_all  = np.concatenate([temp_high, temp_low])
    temp_anom = np.column_stack([
        temp_all,
        rng.uniform(METH_MIN_NORMAL, METH_MAX_NORMAL, n_temp),
        rng.uniform(RAD_MIN_NORMAL,  RAD_MAX_NORMAL,  n_temp),
    ])

    # Methane anomalies: >1.5 ppb
    meth_anom = np.column_stack([
        rng.uniform(TEMP_MIN_NORMAL, TEMP_MAX_NORMAL, n_meth),
        rng.uniform(1.6, 5.0, n_meth),
        rng.uniform(RAD_MIN_NORMAL,  RAD_MAX_NORMAL,  n_meth),
    ])

    # Radiation anomalies: >500 μSv/h (solar flare)
    rad_anom = np.column_stack([
        rng.uniform(TEMP_MIN_NORMAL, TEMP_MAX_NORMAL, n_rad),
        rng.uniform(METH_MIN_NORMAL, METH_MAX_NORMAL, n_rad),
        rng.uniform(501.0, 1000.0, n_rad),
    ])

    return np.vstack([temp_anom, meth_anom, rad_anom])


def compute_zscore_stats(X: np.ndarray) -> dict:
    """Compute per-feature mean and std from normal training data only."""
    return {
        "mean": X.mean(axis=0),
        "std":  X.std(axis=0).clip(min=1e-8),   # avoid zero-division
    }


def self_test(ensemble: dict) -> None:
    """Run a quick sanity check on normal and anomalous samples."""
    from inference import predict as _predict_fn

    # Normal: mid-range NASA REMS values
    normal_result = _predict_fn(
        temperature=0.0,       # mid-range normal
        methane_level=0.5,     # mid-range normal
        radiation=230.0,       # mid-range normal
    )
    print(f"\n✅ Normal veri testi  → is_anomaly: {normal_result['is_anomaly']}")

    # Anomaly: clear solar-flare radiation spike
    anomaly_result = _predict_fn(
        temperature=50.0,      # >40 °C anomaly
        methane_level=2.5,     # >1.5 ppb anomaly
        radiation=650.0,       # >500 μSv/h anomaly
    )
    print(f"✅ Anomali veri testi → is_anomaly: {anomaly_result['is_anomaly']}")


def main() -> None:
    print("✅ Model eğitiliyor...")

    X_normal  = generate_normal_samples(N_NORMAL)
    X_anomaly = generate_anomaly_samples(N_ANOMALY)
    X_all     = np.vstack([X_normal, X_anomaly])

    print(f"   Normal samples  : {len(X_normal)}")
    print(f"   Anomaly samples : {len(X_anomaly)}")
    print(f"   Total           : {len(X_all)}")

    # ── Isolation Forest ─────────────────────────────────────────────────────────
    print("\n🌲 Training Isolation Forest (contamination=0.1) …")
    if_model = IsolationForest(
        n_estimators=200,
        contamination=0.1,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    if_model.fit(X_all)

    # ── Local Outlier Factor ──────────────────────────────────────────────────────
    print("🔍 Training LOF (novelty=True, contamination=0.1) …")
    lof_model = LocalOutlierFactor(
        n_neighbors=20,
        contamination=0.1,
        novelty=True,       # REQUIRED — allows predict() at inference time
        n_jobs=-1,
    )
    lof_model.fit(X_all)

    # ── Z-Score statistics ────────────────────────────────────────────────────────
    print("📊 Computing Z-Score statistics from normal samples …")
    zscore_stats = compute_zscore_stats(X_normal)

    # ── Persist ──────────────────────────────────────────────────────────────────
    ensemble = {
        "if_model":     if_model,
        "lof_model":    lof_model,
        "zscore_stats": zscore_stats,
    }
    joblib.dump(ensemble, MODEL_PATH)
    print(f"\n✅ Model kaydedildi: models/ensemble.joblib")

    # ── Self-test ─────────────────────────────────────────────────────────────────
    self_test(ensemble)

    print("\n🎉 Eğitim tamamlandı. Sunucuyu başlatmak için server.py'yi çalıştırın.")


if __name__ == "__main__":
    main()
