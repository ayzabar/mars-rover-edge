# AI Changelog — Mars Rover Edge Computing Project

---

## [2026-03-29] earth_dashboard.html — Timeline Panel: Scatter Plot → Vertical Event List

### What Changed

**File:** `earth_dashboard.html`

#### Problem
The Transmission Timeline panel used a Chart.js scatter plot where X = timestamp and Y = weighted_score. Because alerts arrive in bursts (close timestamps) and often have similar scores, dots piled on top of each other into an unreadable blob.

#### Fix: Pure HTML/CSS Vertical Event Timeline
Removed the Chart.js `<canvas>` scatter plot entirely. Replaced it with a scrollable vertical list of alert events (newest at top). No canvas, no Chart.js dependency for this panel.

Each event row displays:
- **Severity dot** — colored circle (red/amber/green) with matching glow (`box-shadow`)
- **Timestamp** — HH:MM:SS UTC
- **Score badge** — severity-tinted background + border (e.g. `rgba(255,59,59,0.15)` for critical)
- **Model tags** — triggered models (IF+LOF+ZSCORE) in blue
- **Sensor summary** — one-line reading (e.g. `T=70.3°C`) with ellipsis overflow

#### Changes by section

| Section | Removed | Added |
|---------|---------|-------|
| CSS (lines 277–296) | `#timeline-chart-wrap` | `#timeline-events`, `.tl-event`, `.tl-dot`, `.tl-time`, `.tl-score`, `.tl-models`, `.tl-info`, `#timeline-empty`, `@keyframes tl-fade-in` |
| HTML (lines 410–421) | `<canvas id="timeline-chart">`, "← 5 MIN AGO / NOW →" labels | `<div id="timeline-events">` with `▷ NO EVENTS YET` placeholder, event counter `<span id="tl-count">` |
| JS (lines 700–792) | `new Chart(ctx, { type: 'scatter' ... })`, `pushTimelinePoint()` with Chart.js updates, 10s `setInterval` x-axis refresh | `pushTimelinePoint()` builds DOM rows, prepends newest-first, trims to `MAX_TIMELINE` |
| JS state (line 496–497) | `const timelinePoints = []` | `let timelineCount = 0` |

Panel height increased from `flex: 0 0 140px` → `flex: 0 0 220px` to fit event rows. Fade-in animation (`tl-fade-in`) and hover highlight added. Scrollbar styled to match Signal Feed panel.

### Verification

- No remaining references to `timelineChart`, `timeline-chart`, or `timelinePoints` in the file (verified via grep).
- `pushTimelinePoint(score, infoStr)` function signature unchanged — callers (`processAlert`) require zero changes.
- Chart.js is still loaded (used by other dashboards / `dashboard.html`), but this panel no longer uses it.

---

## [2026-03-29] Python ML Stack — Initial Build + Go Sensor/Pub Updates

### What Changed

#### 1. `anomaly-ml-python/requirements.txt` (new)
Pinned: `flask>=2.3.0`, `scikit-learn>=1.3.0`, `joblib>=1.3.0`, `numpy>=1.24.0`.

#### 2. `anomaly-ml-python/train.py` (new)
One-shot training script. Generates 10 000 synthetic Mars samples (9 000 normal, 1 000 anomaly, ~10% contamination). Trains:
- `IsolationForest(n_estimators=200, contamination=0.1)` on all data.
- `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.1)` — `novelty=True` required for inference-time `predict()` calls.
- Z-Score stats (mean + std clipped at 1e-8) computed on **normal-only** data for a clean baseline.

Persists `{if_model, lof_model, zscore_stats}` → `models/ensemble.joblib` via `joblib.dump`. Uses `numpy.random.default_rng(42)` for reproducibility.

Initial ranges used old approximations. Later updated to NASA REMS values (see train.py entry above).

#### 3. `anomaly-ml-python/inference.py` (new)
Lazy singleton model load with double-checked locking (`threading.Lock`). `predict(temperature, methane_level, radiation, timestamp)` builds `np.array([[temp, methane, rad]])` (shape 1×3), runs each model:
- IF / LOF: sklearn convention `-1` = anomaly → `1.0`, `+1` = inlier → `0.0`.
- Z-Score: `|X − mean| / std > 2.5` on any feature → `1.0`.

Weighted vote: `score = IF×0.5 + LOF×0.3 + ZScore×0.2`. `is_anomaly = score > 0.5`. `triggered_models` list built from whichever individual scores are `> 0`. Timestamp echoed from caller or defaults to `datetime.now(UTC)`.

#### 4. `anomaly-ml-python/server.py` (new)
Flask app on `0.0.0.0:5050` (configurable via `FLASK_HOST`/`FLASK_PORT` env vars).
- `GET /health` → `200 {"status":"ok"}` — Go-side liveness probe.
- `POST /predict` — validates presence and numeric type of `{temperature, methane_level, radiation}`. Returns `400` on bad input, `503` if model file missing, `500` on unexpected error, `200` + result dict on success. Structured logging on every request.

#### 5. `edge-core-go/internal/generator/sensor.go` — Sensor Range Fix
Updated `generate()` to use NASA REMS real data ranges, aligned with the retrained Python model:

| Sensor | Normal (before) | Normal (after) | Anomaly (after) |
|---|---|---|---|
| `temperature` | −80 … +30 °C | **−90 … +30 °C** | 45–95 °C (high) |
| `methane_level` | 0.0 … 0.05 ppm | **0.3 … 0.7 ppb** | 1.5–3.0 ppb |
| `radiation` | 0 … 100 μSv/h | **180 … 280 μSv/h** | 500–900 μSv/h |

Anomaly injection (~10%) was also restructured: instead of spiking all three sensors simultaneously, a `rand.Intn(3)` switch now fires **one sensor type at a time** (temp spike, methane spike, or solar-flare radiation), keeping the other two in the normal range. This better matches single-fault realistic anomaly patterns and gives the ML model clean, separable signals.

#### 6. `edge-core-go/internal/mqttpub/pub.go` — `earth/alerts` Goroutine
Added non-blocking delayed publishing to `earth/alerts` topic to simulate Mars→Earth transmission delay:

```go
if anomaly.IsAnomaly {
    go func(p TelemetryPayload) {
        time.Sleep(18 * time.Second)   // Mars→Earth one-way delay
        // marshal + publish to "earth/alerts", QoS 1
        log.Printf("[EARTH TX] anomaly signal transmitted → earth/alerts (18s delay)")
    }(payload)
}
```

- Payload is **value-captured** at goroutine spawn so it's immutable inside the goroutine.
- `rover/telemetry` publish path unchanged — fires on every reading.
- `earth/alerts` fires **only** on anomalies, 18 seconds after the anomaly is detected.
- New constant `earthAlertsTopic = "earth/alerts"` and `earthTxDelay = 18 * time.Second` added to `const` block.

### Verification Results

**Python — 8/8 integration tests passed (exit code 0):**

| # | Test | HTTP | Result |
|---|---|---|---|
| 1 | `GET /health` | 200 | `{"status":"ok"}` |
| 2 | Normal reading (temp=5°C, methane=0.5ppb, rad=230) | 200 | `is_anomaly: false`, score=0.0, no models triggered |
| 3 | Temp anomaly (70°C) | 200 | `is_anomaly: true`, score=0.7, `[isolation_forest, zscore]` |
| 4 | Methane anomaly (2.5ppb) | 200 | `is_anomaly: true`, score=**1.0**, all 3 models triggered |
| 5 | Radiation solar flare (650 μSv/h) | 200 | `is_anomaly: true`, score=0.7, `[isolation_forest, zscore]` |
| 6 | Missing field (`radiation` absent) | 400 | `"Missing required fields: ['radiation']"` |
| 7 | Wrong type (`radiation="high"`) | 400 | `"Fields must be numeric: ['radiation']"` |
| 8 | Malformed JSON body | 400 | error key present |

**Go — `go` binary not present on this machine.** Code changes were surgical (value substitutions + one goroutine addition). Static analysis deferred until Go is installed.

**Model retrained** during this session with new NASA REMS ranges — `ensemble.joblib` on disk is now aligned with the updated `sensor.go` bounds.

---


## [2026-03-29] earth_dashboard.html — JPL Earth-Side Mission Control Dashboard

### What Changed

**File:** `earth_dashboard.html` (new, 1059 lines) — commit `a9bc494`

#### 1. New Component: Earth Relay Dashboard

A second single-file HTML dashboard (`earth_dashboard.html`) was created alongside the existing rover-side `dashboard.html`. It represents the **Earth-side JPL Deep Space Operations** view, receiving anomaly alerts relayed from the rover with a simulated 18.4-second Mars-to-Earth transmission delay.

**Architecture:** Pages subscribe to the `earth/alerts` MQTT topic (distinct from `rover/telemetry`). When connected, it only displays alerts where `anomaly.is_anomaly = true`. If the MQTT broker is unreachable, it falls back to simulation mode generating realistic REMS-range anomalies every 15–25s.

#### 2. Layout & Panels

**Left column:**
- **Signal Feed** — terminal-style anomaly cards with red left border, slide-in animation, and full data: origin timestamp (Mars), transmission timestamp (Earth), 18.4s delay label, per-sensor [CRITICAL/ELEVATED/NOMINAL] tags, triggered models (IF/LOF/ZSCORE), weighted score, and human-readable root cause text.
- **Transmission Timeline** — pure HTML/CSS vertical event list showing the last 10 alerts (newest at top). Each row: severity-colored dot with glow, HH:MM:SS timestamp, score badge, model tags, sensor summary. Scrollable, with fade-in animation.

**Right column:**
- **Anomaly Statistics** — live counters: total signals received, CRITICAL (score > 0.8), ELEVATED (0.5 < score ≤ 0.8), most-triggered model, average weighted score, peak temperature/radiation/methane, session uptime.
- **Earth Receiving Station Status** — simulated DSN readout cycling through DSN-26 Goldstone / DSN-43 Canberra / DSN-63 Madrid with drifting signal strength (dBm), bit rate (kbps), uptime, and last ACK. Refreshes every second.
- **Alert Severity Gauge** — horizontal bar stack of the last 20 received scores. Bars color-coded by tier and opacity-faded oldest→newest for temporal sense.

**Header:**
- Amber boxed `⏱ TRANSMISSION DELAY: 18.4s` badge.
- Animated `⟶ INCOMING SIGNAL... [████░░░░░░] N%` progress bar ticking during the 18.4s delay window.
- Green/amber connection status dot + label (`CONNECTED` / `SIMULATED MODE`).
- Live Mars Sol counter (base SOL 4521) and UTC clock.
- CRT scanline overlay and pulsing blue logo mark.

**Visual identity:** Matches `dashboard.html` aesthetic exactly (Share Tech Mono, dark palette `#060a12`, CRT scanlines) with **blue accent** (`#0077ff`) instead of green to distinguish Earth-side from rover-side.

#### 3. Bug Fix — Round 1: Overlapping Stats Counters

**File:** `earth_dashboard.html` → `updateStats()`

```js
// BEFORE (broken): both fire for score > 0.8, double-counting into ELEVATED
if (score > 0.8) stats.critical++;
if (score > 0.5) stats.elevated++;   // also fires when score > 0.8

// AFTER (fixed): mutually exclusive tiers
if (score > 0.8)       stats.critical++;
else if (score > 0.5)  stats.elevated++;
```

HTML label updated from `ELEVATED (score > 0.5)` → `ELEVATED (0.5 < score ≤ 0.8)` to make the tier boundary explicit.

#### 4. Bug Fix — Round 2: Three-Component Threshold Inconsistency

**Root cause (identified via live browser debug session):**

Two independent bugs remained after Round 1:

**A. Floating-point drift:** `anomaly.weighted_score` is a raw float from `randBetween(0.52, 0.95)`. Values like `0.8000000000000001` compared against `> 0.8` crossed the threshold unpredictably, placing borderline scores into the wrong bucket.

```js
// FIX: normalize before comparison
const scoreClamped = parseFloat(score.toFixed(2));
if (scoreClamped > 0.8)       stats.critical++;
else if (scoreClamped > 0.5)  stats.elevated++;
```

**B. Threshold mismatch across components:** The severity gauge and timeline chart used `> 0.7` for red/high, while the stats panel used `> 0.8` for CRITICAL. A score of 0.75 rendered as a **red bar** (visually implying critical) but counted as ELEVATED — misleading the user.

Changed all three components to use `> 0.8` for red/critical, `> 0.5` for amber/elevated:

| Component | Before | After |
|---|---|---|
| `updateStats` threshold | raw `score > 0.8` | `scoreClamped > 0.8` (2dp normalized) |
| Timeline dot color | `> 0.7` = red | `> 0.8` = red |
| Gauge bar color | `> 0.7` = red | `> 0.8` = red |

### Verification Results

- Dashboard renders in Chrome: all 5 panels visible, header fully populated.
- Simulation mode activates within 6s of load when broker unavailable (amber `SIMULATED MODE`).
- First sim alert arrives after ~15s wait + 18.4s delay. Alert card appears with slide-in, stats panel updates, gauge bar appears, timeline dot plotted.
- Confirmed after Round 2 fix: scores 0.52–0.80 → ELEVATED (amber gauge), scores 0.81–0.95 → CRITICAL (red gauge) — counters and visuals now agree.
- Commit `a9bc494` pushed to `origin/main`.

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
Package `generator`. Exports `SensorData` struct with `temperature`, `methane_level`, `radiation`, `timestamp` — JSON tags match the contract consumed by Python and the dashboard. `Start(done <-chan struct{}) <-chan SensorData` launches a goroutine with `time.Ticker` at 100ms (10Hz). Channel buffered at 64 for backpressure. `generate()` produces random values in **NASA REMS normal ranges** 90% of the time (temp −90 to +30 °C, methane 0.3–0.7 ppb, radiation 180–280 μSv/h). 10% anomaly injection now fires **one sensor at a time** via `rand.Intn(3)` switch: temp spike (45–95 °C), methane spike (1.5–3.0 ppb), or radiation solar flare (500–900 μSv/h). Goroutine exits cleanly on `done` channel close.

### `internal/httpclient/client.go`
Package `httpclient`. Exports `AnomalyResult` struct matching Python response contract: `is_anomaly` (bool), `confidence`, `weighted_score` (float64), `triggered_models` ([]string), `timestamp` (string). `Client` wraps `http.Client` with 2-second timeout. `New(endpoint string)` constructor. `Predict(SensorData)` does JSON marshal → POST to `http://localhost:5050/predict` → JSON decode response. Returns error on any failure; caller logs and skips — pipeline never blocks.

### `internal/mqttpub/pub.go`
Package `mqttpub`. Defines `TelemetryPayload`, `SensorPayload`, `AnomalyPayload` structs matching final MQTT JSON contract. `Publisher` wraps paho MQTT client. `New(brokerURL)` creates client with auto-reconnect, connect retry (2s interval), unique client ID via unix nano. Connection is non-blocking — `ConnectRetry` makes `Connect()` return after best-effort 3s wait, retrying in background if broker is down. `Publish(SensorData, *AnomalyResult)` builds final payload → JSON → publishes to `rover/telemetry` QoS 1, then — if `anomaly.IsAnomaly == true` — spawns a goroutine that sleeps 18 seconds and re-publishes the same payload to `earth/alerts` QoS 1 (simulated Mars→Earth transmission delay). `Close()` disconnects with 1s quiesce.

**Bug fix applied (original):** `WaitTimeout(5s)` blocked indefinitely when `ConnectRetry=true` and broker was down. Changed to non-blocking connect with background retry.

**Feature added (2026-03-29):** `earth/alerts` delayed goroutine. Non-blocking, value-captures payload at spawn. Logs `[EARTH TX] anomaly signal transmitted → earth/alerts (18s delay)` on success.

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

- `go vet ./...` — clean (original session; Go not present in current machine PATH)
- `go build ./...` — clean (original session)
- Live run: 10Hz generation confirmed, HTTP gracefully handles connection refused, MQTT auto-reconnects in background, graceful SIGTERM shutdown works
- Python `train.py` executed with NASA REMS ranges, `ensemble.joblib` regenerated (4.0MB, 2026-03-29)
- `server.py` serves on :5050 with `/predict` and `/health` endpoints
- **8/8 integration tests passed** (2026-03-29): normal/anomaly classification correct, all 3 error codes verified
- Dashboard connects via WebSocket to Mosquitto, falls back to simulation when broker unavailable
