"""
server.py — Flask HTTP server for Mars Rover anomaly detection.

Listens on 0.0.0.0:5050 and exposes:
    POST /predict   — accepts sensor JSON, returns anomaly result JSON
    GET  /health    — returns 200 OK so the Go service can probe liveness

JSON contract (from CONTEXT.md):

Input:
    {
        "temperature"  : 23.4,
        "methane_level": 0.012,
        "radiation"    : 55.2,
        "timestamp"    : "2025-01-01T12:00:00Z"   # optional / echoed back
    }

Output:
    {
        "is_anomaly"      : true,
        "confidence"      : 0.83,
        "weighted_score"  : 0.76,
        "triggered_models": ["isolation_forest", "lof"],
        "timestamp"       : "2025-01-01T12:00:00Z"
    }
"""

import logging
import os
import sys

from flask import Flask, jsonify, request

from inference import predict

# ── Logging ───────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

PORT = int(os.getenv("FLASK_PORT", 5050))
HOST = os.getenv("FLASK_HOST", "0.0.0.0")

# ── Required fields and their expected types ──────────────────────────────────────
_REQUIRED_FIELDS: dict[str, type] = {
    "temperature":   (int, float),
    "methane_level": (int, float),
    "radiation":     (int, float),
}


# ── Routes ────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe — always returns 200."""
    return jsonify({"status": "ok"}), 200


@app.route("/predict", methods=["POST"])
def predict_endpoint():
    """
    Accept a sensor reading and return an anomaly prediction.

    Returns 400 if the body is missing or malformed.
    Returns 500 with an error message if inference fails unexpectedly.
    """
    data = request.get_json(silent=True)

    # ── Validate payload ──────────────────────────────────────────────────────────
    if data is None:
        logger.warning("Received request with no JSON body.")
        return jsonify({"error": "Request body must be valid JSON."}), 400

    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        logger.warning("Missing fields in request: %s", missing)
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    type_errors = [
        f for f, t in _REQUIRED_FIELDS.items()
        if not isinstance(data[f], t)
    ]
    if type_errors:
        logger.warning("Type errors in request fields: %s", type_errors)
        return jsonify({"error": f"Fields must be numeric: {type_errors}"}), 400

    temperature   = float(data["temperature"])
    methane_level = float(data["methane_level"])
    radiation     = float(data["radiation"])
    timestamp     = data.get("timestamp")   # optional; echoed back if present

    logger.info(
        "Predicting — temp=%.2f  methane=%.4f  radiation=%.2f",
        temperature, methane_level, radiation,
    )

    # ── Run inference ─────────────────────────────────────────────────────────────
    try:
        result = predict(
            temperature=temperature,
            methane_level=methane_level,
            radiation=radiation,
            timestamp=timestamp,
        )
    except FileNotFoundError as exc:
        logger.error("Model not found: %s", exc)
        return jsonify({"error": str(exc)}), 503  # Service Unavailable
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Unexpected inference error: %s", exc)
        return jsonify({"error": "Internal inference error."}), 500

    logger.info(
        "Result — is_anomaly=%s  score=%.4f  models=%s",
        result["is_anomaly"],
        result["weighted_score"],
        result["triggered_models"],
    )

    return jsonify(result), 200


# ── Entry point ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Starting Mars Rover ML server on %s:%d", HOST, PORT)
    logger.info("   POST /predict   — anomaly inference")
    logger.info("   GET  /health    — liveness probe")
    app.run(host=HOST, port=PORT, debug=False)
