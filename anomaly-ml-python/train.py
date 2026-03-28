"""
train.py — One-shot training script for the Mars Rover anomaly detection ensemble.

Run ONCE before starting the server:
    python train.py

Produces:
    models/ensemble.joblib  — serialised {if_model, lof_model, zscore_stats}
"""

import os
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

# ── Output directory ────────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODELS_DIR, exist_ok=True)
MODEL_PATH = os.path.join(MODELS_DIR, "ensemble.joblib")

# ── Sensor value ranges (from CONTEXT.md) ───────────────────────────────────────
#   temperature  : -80 … +30  (normal)  |  >50 or <-100 (anomaly)
#   methane_level:  0.0 … 0.05 (normal) |  >0.1  (anomaly)
#   radiation    :  0 … 100   (normal)  |  >200  (anomaly)

RANDOM_STATE = 42
N_NORMAL = 9_000
N_ANOMALY = 1_000   # ~10 % contamination — matches IsolationForest/LOF setting

rng = np.random.default_rng(RANDOM_STATE)


def generate_normal_samples(n: int) -> np.ndarray:
    """Draw samples from the nominal Mars operating envelope."""
    temperature   = rng.uniform(-80.0, 30.0, n)
    methane_level = rng.uniform(0.0, 0.05, n)
    radiation     = rng.uniform(0.0, 100.0, n)
    return np.column_stack([temperature, methane_level, radiation])


def generate_anomaly_samples(n: int) -> np.ndarray:
    """Draw samples from anomalous regions (beyond safe thresholds)."""
    # Split anomalies across the three sensor types
    n_temp   = n // 3
    n_meth   = n // 3
    n_rad    = n - n_temp - n_meth

    # Temperature anomalies: >50 or <-100
    temp_high = rng.uniform(51.0, 120.0, n_temp // 2)
    temp_low  = rng.uniform(-150.0, -101.0, n_temp - n_temp // 2)
    temp_all  = np.concatenate([temp_high, temp_low])
    temp_anom = np.column_stack([
        temp_all,
        rng.uniform(0.0, 0.05, n_temp),
        rng.uniform(0.0, 100.0, n_temp),
    ])

    # Methane anomalies: >0.1 ppm
    meth_anom = np.column_stack([
        rng.uniform(-80.0, 30.0, n_meth),
        rng.uniform(0.11, 0.5, n_meth),
        rng.uniform(0.0, 100.0, n_meth),
    ])

    # Radiation anomalies: >200 μSv/h
    rad_anom = np.column_stack([
        rng.uniform(-80.0, 30.0, n_rad),
        rng.uniform(0.0, 0.05, n_rad),
        rng.uniform(201.0, 600.0, n_rad),
    ])

    return np.vstack([temp_anom, meth_anom, rad_anom])


def compute_zscore_stats(X: np.ndarray) -> dict:
    """Compute per-feature mean and std from normal training data only."""
    return {
        "mean": X.mean(axis=0),
        "std":  X.std(axis=0).clip(min=1e-8),   # avoid zero-division
    }


def main() -> None:
    print("🚀 Generating synthetic Mars sensor data …")
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
    print("   ✅ Isolation Forest trained.")

    # ── Local Outlier Factor (novelty=True for inference-time predict()) ─────────
    print("\n🔍 Training LOF (novelty=True, contamination=0.1) …")
    lof_model = LocalOutlierFactor(
        n_neighbors=20,
        contamination=0.1,
        novelty=True,       # REQUIRED — allows predict() at inference time
        n_jobs=-1,
    )
    lof_model.fit(X_all)
    print("   ✅ LOF trained.")

    # ── Z-Score statistics (computed on normal data only for a clean baseline) ──
    print("\n📊 Computing Z-Score statistics from normal samples …")
    zscore_stats = compute_zscore_stats(X_normal)
    print(f"   mean : {zscore_stats['mean']}")
    print(f"   std  : {zscore_stats['std']}")
    print("   ✅ Z-Score stats computed.")

    # ── Persist ──────────────────────────────────────────────────────────────────
    ensemble = {
        "if_model":     if_model,
        "lof_model":    lof_model,
        "zscore_stats": zscore_stats,
    }
    joblib.dump(ensemble, MODEL_PATH)
    print(f"\n💾 Ensemble saved → {MODEL_PATH}")
    print("\n🎉 Training complete. You can now start server.py.")


if __name__ == "__main__":
    main()
