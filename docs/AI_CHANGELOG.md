# AI Changelog — Mars Rover Edge Computing Project

---

## [2026-03-29] train.py — NASA REMS Data Ranges + Turkish Output + Self-Test

### What Changed

**File:** `anomaly-ml-python/train.py`

#### 1. NASA REMS Real Data Ranges Applied
Previous ranges were approximations. Updated to match real NASA REMS sensor data published from Curiosity rover:

| Sensor          | Normal Range            | Anomaly Threshold               |
|-----------------|-------------------------|---------------------------------|
| Temperature     | −90 … +30 °C            | > 40 °C or < −110 °C            |
| Radiation       | 180 … 280 μSv/h         | > 500 μSv/h (solar flare)       |
| Methane Level   | 0.3 … 0.7 ppb           | > 1.5 ppb                       |

Both `generate_normal_samples()` and `generate_anomaly_samples()` now use these corrected bounds. Constants defined at module level (`TEMP_MIN_NORMAL`, `RAD_MAX_NORMAL`, `METH_ANOMALY`, etc.) for clarity and easy maintenance.

#### 2. Turkish Status Messages
Output messages updated to Turkish per project convention:
- `✅ Model eğitiliyor...`
- `✅ Model kaydedildi: models/ensemble.joblib`

#### 3. Self-Test Added
`self_test()` function runs at the end of training, calling `inference.predict()` with:
- A **normal** sample (temp=0 °C, methane=0.5 ppb, radiation=230 μSv/h) → verifies `is_anomaly: False`
- An **anomalous** sample (temp=50 °C, methane=2.5 ppb, radiation=650 μSv/h) → verifies `is_anomaly: True`

#### 4. Windows UTF-8 Fix
Added `sys.stdout` reconfiguration at startup to force UTF-8 encoding on Windows terminals using Turkish locale (cp1254), preventing `UnicodeEncodeError` on emoji/Turkish characters.

### Verification Results

```
✅ Model eğitiliyor...
   Normal samples  : 9000
   Anomaly samples : 1000
   Total           : 10000

🌲 Training Isolation Forest (contamination=0.1) …
🔍 Training LOF (novelty=True, contamination=0.1) …
📊 Computing Z-Score statistics from normal samples …

✅ Model kaydedildi: models/ensemble.joblib

✅ Normal veri testi  → is_anomaly: False
✅ Anomali veri testi → is_anomaly: True

🎉 Eğitim tamamlandı. Sunucuyu başlatmak için server.py'yi çalıştırın.
```

- `models/ensemble.joblib` regenerated: **4.0 MB** (2026-03-29 01:09:20)
- Run command: `$env:PYTHONIOENCODING="utf-8"; python train.py`

---

## Project Overview

Mars Rover edge computing simulation. A Go backend generates synthetic sensor data at 10Hz, sends it to a Python Flask ML server for anomaly detection (3-model weighted voting ensemble), then publishes combined sensor+anomaly results via MQTT to a web dashboard. Stack: Go 1.22+ → Python 3.10+ (Flask) → Eclipse Mosquitto (MQTT) → Web Dashboard (HTML/JS/Chart.js). All inter-service communication is HTTP/JSON REST (Go↔Python) and MQTT/JSON (Go→Dashboard via WebSocket). No gRPC/Protobuf.

## Current Project State (as of latest commit)

All 3 major components are implemented and merged to `main`. The trained ML model exists (`ensemble.joblib`, 4.1MB). A web-based dashboard replaces the original Unity plan.

### Git History (reverse chronological)

```
7f2a7f5 Merge origin/main into main
a5a1d16 dashboard.html fixed push main
6457b6b Merge pull request #1 from ayzabar/frontend-dev
d214814 Fronted (dashboard.html) pushed
542ec67 add docker + bug fixes, tests
d862291 add trained ensemble model
37457fd anomaly-ml-python is done
3de34db edge-core-go built + gitignore
557d972 added context
15e938f Initial commit
```

---

## Component 1: Go Edge Core (`edge-core-go/`)

**Status:** Complete, compiles clean (`go vet` + `go build` pass).

### `go.mod`
Module `edge-core-go`, Go 1.22. Single external dependency: `github.com/eclipse/paho.mqtt.golang v1.5.0`. Indirect deps: gorilla/websocket, golang.org/x/net, golang.org/x/sync.

### `internal/generator/sensor.go`
Package `generator`. Exports `SensorData` struct with `temperature`, `methane_level`, `radiation`, `timestamp` — JSON tags match the contract consumed by Python and the dashboard. `Start(done <-chan struct{}) <-chan SensorData` launches a goroutine with `time.Ticker` at 100ms (10Hz). Channel buffered at 64 for backpressure. `generate()` produces random values in normal Mars ranges 90% of the time (temp -80 to 30°C, methane 0-0.05 ppm, radiation 0-100 μSv/h). 10% anomaly injection (temp 55-120, methane 0.12-0.50, radiation 220-500). Goroutine exits cleanly on `done` channel close.

### `internal/httpclient/client.go`
Package `httpclient`. Exports `AnomalyResult` struct matching Python response contract: `is_anomaly` (bool), `confidence`, `weighted_score` (float64), `triggered_models` ([]string), `timestamp` (string). `Client` wraps `http.Client` with 2-second timeout. `New(endpoint string)` constructor. `Predict(SensorData)` does JSON marshal → POST to `http://localhost:5050/predict` → JSON decode response. Returns error on any failure; caller logs and skips — pipeline never blocks.

### `internal/mqttpub/pub.go`
Package `mqttpub`. Defines `TelemetryPayload`, `SensorPayload`, `AnomalyPayload` structs matching final MQTT JSON contract. `Publisher` wraps paho MQTT client. `New(brokerURL)` creates client with auto-reconnect, connect retry (2s interval), unique client ID via unix nano. Connection is non-blocking — `ConnectRetry` makes `Connect()` return after best-effort 3s wait, retrying in background if broker is down. `Publish(SensorData, *AnomalyResult)` builds final payload → JSON → publishes to `rover/telemetry` QoS 1. `Close()` disconnects with 1s quiesce.

**Bug fix applied:** Original code used `WaitTimeout(5s)` which blocked indefinitely when `ConnectRetry=true` and broker was down. Changed to non-blocking connect with background retry so startup never hangs.

### `cmd/main.go`
Package `main`. Wires full pipeline: `generator.Start(done)` → goroutine reads sensor channel → `mlClient.Predict(data)` → on error: log + skip + continue → on success: log anomalies → `pub.Publish(data, result)`. `os.Signal` (SIGINT/SIGTERM) graceful shutdown via `done` channel. `log.Lmicroseconds` timestamps.

---

## Component 2: Python ML Server (`anomaly-ml-python/`)

**Status:** Complete. Model trained and saved.

### `train.py`
One-shot training script. Generates synthetic Mars sensor data: 9000 normal + 1000 anomaly samples (~10% contamination). Trains 3 models:
- `IsolationForest(n_estimators=200, contamination=0.1)` — fit on all data
- `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.1)` — `novelty=True` required for inference-time `predict()`
- Z-Score stats (mean + std) — computed on normal data only for clean baseline, std clipped at 1e-8 to avoid zero-division

Saves everything as `models/ensemble.joblib` (4.1MB). Uses `numpy.random.default_rng(42)` for reproducibility.

### `inference.py`
Lazy-loads `ensemble.joblib` with double-checked locking (`threading.Lock`). `predict(temperature, methane_level, radiation, timestamp)` builds feature vector `[temp, methane, rad]`, runs all 3 models:
- IF: `predict()` returns -1 (anomaly) or +1 (inlier) → binary 1.0/0.0
- LOF: same convention
- Z-Score: `|z| > 2.5` on any feature → 1.0

Weighted vote: `score = IF*0.5 + LOF*0.3 + ZSCORE*0.2`. If `score > 0.5` → `is_anomaly = True`. Confidence = weighted_score directly (max possible = 1.0). Returns dict matching JSON contract. Timestamp echoed or defaults to UTC now.

### `server.py`
Flask app on `0.0.0.0:5050`. Two routes:
- `GET /health` — returns `{"status": "ok"}` (liveness probe)
- `POST /predict` — validates JSON body (checks required fields `temperature`, `methane_level`, `radiation` exist and are numeric), calls `inference.predict()`, returns result. Error handling: 400 for bad input, 503 if model file missing, 500 for unexpected errors.

Structured logging to stdout. Host/port configurable via `FLASK_HOST`/`FLASK_PORT` env vars.

### `requirements.txt`
```
flask
scikit-learn
joblib
numpy
```

### `models/ensemble.joblib`
Trained model file, 4.1MB. Contains dict: `{if_model, lof_model, zscore_stats}`.

---

## Component 3: Web Dashboard (`dashboard.html` + JS libs)

**Status:** Complete. Replaces the originally planned Unity3D dashboard.

### Architecture Decision
Team pivoted from Unity3D to a single-file HTML dashboard. This eliminates the Unity build/dependency chain and allows the dashboard to run in any browser. Connects to Mosquitto via WebSocket on port 9001.

### `dashboard.html` (1014 lines)
Single-file mission control dashboard with CRT/retro aesthetic using Share Tech Mono font. 2-column layout:

**Left column:**
- **Anomaly Log Matrix** — visual grid of pills (blue=normal, red=anomaly). New readings push rows from top, older rows fade. 12 columns × 10 rows. Animated slide-in.
- **Methane Gas Level chart** — real-time Chart.js line chart with red dashed threshold at 0.1 ppm. Anomaly points shown as red triangles, normal as white circles. Max 60 data points.
- **Surface Temperature chart** — same style, threshold at 50°C.

**Right column:**
- **Average Values (Rolling 30s)** — displays rolling averages for methane, temperature, radiation from last 30 readings.
- **Rover Diagnostics** — simulated subsystem readouts (power/MMRTG, battery status with ASCII bar, wheel RPM, CPU temp, RAM, signal strength, uptime). Values drift randomly every 5s for realism.
- **Event Log (Terminal)** — scrolling log with timestamps. Anomalies show triggered models (IF/LOF/ZSCORE), weighted score, and root cause text. Normal readings logged at 10% rate to reduce spam. Max 200 lines retained.

**MQTT Connection:**
- Connects to `ws://localhost:9001` using `mqtt.min.js` (paho/MQTT.js browser client)
- Subscribes to `rover/telemetry` topic
- On connection: status dot turns green, label shows "CONNECTED"
- On failure/disconnect: falls back to **simulation mode** (amber dot, "SIMULATED MODE")
- Simulation generates synthetic telemetry at 1Hz with ~10% anomaly rate, matching Go generator ranges

**Dependencies (vendored at project root):**
- `chart.min.js` — Chart.js (205KB)
- `mqtt.min.js` — MQTT browser client (310KB)

---

## Component 4: Infrastructure

### `docker-compose.yml`
Single service: `eclipse-mosquitto:2`. Ports `1883` (MQTT) + `9001` (WebSocket). Mounts `mosquitto/mosquitto.conf`. No deprecated `version` field.

### `mosquitto/mosquitto.conf`
Listener 1883 (MQTT default protocol), listener 9001 (WebSocket protocol for browser dashboard). Anonymous access enabled.

### `.gitignore`
Covers: Go binaries/vendor, Python __pycache__/venv/.joblib models, Unity artifacts (legacy, kept for safety), Docker Mosquitto data/log, IDE files (.idea/.vscode), OS files (.DS_Store).

---

## Data Flow (End to End)

```
Go generator (10Hz)
    → channel
    → Go HTTP POST /predict
    → Python Flask (inference.py: IF*0.5 + LOF*0.3 + ZSCORE*0.2)
    → Go receives AnomalyResult
    → Go MQTT publish "rover/telemetry" (QoS 1, port 1883)
    → Mosquitto broker
    → Dashboard subscribes via WebSocket (port 9001)
    → Chart.js renders real-time charts + anomaly matrix + event log
```

If MQTT is unavailable, dashboard runs in simulation mode with synthetic data at 1Hz.

## JSON Contracts (immutable)

**Go→Python (POST /predict):**
```json
{"temperature":23.4,"methane_level":0.012,"radiation":55.2,"timestamp":"2025-01-01T12:00:00Z"}
```

**Python→Go (response):**
```json
{"is_anomaly":true,"confidence":0.83,"weighted_score":0.76,"triggered_models":["isolation_forest","lof"],"timestamp":"2025-01-01T12:00:00Z"}
```

**Go→MQTT→Dashboard (final telemetry):**
```json
{"sensor":{"temperature":23.4,"methane_level":0.012,"radiation":55.2},"anomaly":{"is_anomaly":true,"confidence":0.83,"weighted_score":0.76,"triggered_models":["isolation_forest","lof"]},"timestamp":"2025-01-01T12:00:00Z"}
```

## Verification Results

- `go vet ./...` — clean
- `go build ./...` — clean
- Live run: 10Hz generation confirmed, HTTP gracefully handles connection refused, MQTT auto-reconnects in background, graceful SIGTERM shutdown works
- Python `train.py` executed, `ensemble.joblib` generated (4.1MB)
- `server.py` serves on :5050 with `/predict` and `/health` endpoints
- Dashboard connects via WebSocket to Mosquitto, falls back to simulation when broker unavailable
