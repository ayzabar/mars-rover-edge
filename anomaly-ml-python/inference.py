"""
inference.py — Weighted voting ensemble for Mars Rover anomaly detection.

Contract (from CONTEXT.md §PYTHON):
    Input  : temperature (°C), methane_level (ppm), radiation (μSv/h)
    Output : {
        "is_anomaly"      : bool,
        "confidence"      : float  [0.0 – 1.0],
        "weighted_score"  : float  [0.0 – 1.0],
        "triggered_models": list[str],
        "timestamp"       : str    (ISO-8601, echoed from caller)
    }

Ensemble weights:
    IsolationForest : 0.50
    LOF             : 0.30
    Z-Score         : 0.20

Decision threshold: weighted_score > 0.5
"""

import os
import threading
from datetime import datetime, timezone
from typing import Optional

import joblib
import numpy as np

# ── Model loading (lazy, thread-safe, loaded once) ───────────────────────────────
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "ensemble.joblib")
_ensemble: Optional[dict] = None
_lock = threading.Lock()

ZSCORE_THRESHOLD = 2.5   # |z| > this → sensor is anomalous

WEIGHTS = {
    "isolation_forest": 0.50,
    "lof":              0.30,
    "zscore":           0.20,
}

ANOMALY_THRESHOLD = 0.5  # weighted_score above this → is_anomaly = True


def _load_ensemble() -> dict:
    """Load (and cache) the trained models from disk."""
    global _ensemble
    if _ensemble is None:
        with _lock:
            if _ensemble is None:   # double-checked locking
                if not os.path.exists(_MODEL_PATH):
                    raise FileNotFoundError(
                        f"Model file not found: {_MODEL_PATH}\n"
                        "Run `python train.py` first to generate the ensemble."
                    )
                _ensemble = joblib.load(_MODEL_PATH)
    return _ensemble


def _isolation_forest_score(model, X: np.ndarray) -> float:
    """Return 1.0 (anomaly) or 0.0 (normal) from Isolation Forest."""
    # sklearn convention: predict() returns -1 for anomaly, +1 for inlier
    prediction = model.predict(X)[0]
    return 1.0 if prediction == -1 else 0.0


def _lof_score(model, X: np.ndarray) -> float:
    """Return 1.0 (anomaly) or 0.0 (normal) from LOF."""
    prediction = model.predict(X)[0]
    return 1.0 if prediction == -1 else 0.0


def _zscore_score(stats: dict, X: np.ndarray) -> float:
    """
    Return 1.0 if ANY feature z-score exceeds ZSCORE_THRESHOLD, else 0.0.
    z = |X - mean| / std
    """
    z = np.abs((X[0] - stats["mean"]) / stats["std"])
    return 1.0 if np.any(z > ZSCORE_THRESHOLD) else 0.0


def predict(
    temperature: float,
    methane_level: float,
    radiation: float,
    timestamp: Optional[str] = None,
) -> dict:
    """
    Run the weighted-voting ensemble and return the anomaly result dict.

    Parameters
    ----------
    temperature   : float  — °C
    methane_level : float  — ppm
    radiation     : float  — μSv/h
    timestamp     : str    — ISO-8601; echoed back in the response.
                             Defaults to current UTC time if None.

    Returns
    -------
    dict matching the Go → Python JSON contract defined in CONTEXT.md.
    """
    ensemble = _load_ensemble()

    # Feature vector: shape (1, 3)
    X = np.array([[temperature, methane_level, radiation]])

    # ── Individual model predictions ─────────────────────────────────────────────
    if_result  = _isolation_forest_score(ensemble["if_model"],  X)
    lof_result = _lof_score(ensemble["lof_model"], X)
    z_result   = _zscore_score(ensemble["zscore_stats"], X)

    # ── Weighted vote ─────────────────────────────────────────────────────────────
    weighted_score = (
        if_result  * WEIGHTS["isolation_forest"]
        + lof_result * WEIGHTS["lof"]
        + z_result   * WEIGHTS["zscore"]
    )

    is_anomaly = weighted_score > ANOMALY_THRESHOLD

    # ── Triggered models ──────────────────────────────────────────────────────────
    triggered_models: list[str] = []
    if if_result  > 0: triggered_models.append("isolation_forest")
    if lof_result > 0: triggered_models.append("lof")
    if z_result   > 0: triggered_models.append("zscore")

    # ── Confidence: normalise weighted_score to [0, 1] ───────────────────────────
    # The maximum possible weighted_score when all models fire is 1.0, so we can
    # use it directly as a proxy for confidence.
    confidence = round(float(weighted_score), 4)

    # ── Timestamp ─────────────────────────────────────────────────────────────────
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()

    return {
        "is_anomaly":       bool(is_anomaly),
        "confidence":       confidence,
        "weighted_score":   round(float(weighted_score), 4),
        "triggered_models": triggered_models,
        "timestamp":        timestamp,
    }
