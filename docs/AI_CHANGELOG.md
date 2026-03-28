# AI Changelog — Mars Rover Edge Computing Project

## Project Overview

Mars Rover edge computing simulation. A Go backend generates synthetic sensor data at 10Hz, sends it to a Python Flask ML server for anomaly detection (3-model weighted voting ensemble), then publishes combined sensor+anomaly results via MQTT to a Unity 3D dashboard. Stack: Go 1.22+ → Python 3.10+ (Flask) → Eclipse Mosquitto (MQTT) → Unity3D (C#). All inter-service communication is HTTP/JSON REST (Go↔Python) and MQTT/JSON (Go→Unity). No gRPC/Protobuf.

## Files Created

### Go Edge Core (`edge-core-go/`)

#### `go.mod`
Go module `edge-core-go` with single external dependency: `github.com/eclipse/paho.mqtt.golang v1.5.0`. Indirect deps: gorilla/websocket, golang.org/x/net, golang.org/x/sync.

#### `internal/generator/sensor.go`
Package `generator`. Exports `SensorData` struct with `temperature`, `methane_level`, `radiation`, `timestamp` — JSON tags match the contract consumed by Python and Unity. `Start(done <-chan struct{}) <-chan SensorData` launches a goroutine with `time.Ticker` at 100ms (10Hz). Channel buffered at 64 to absorb backpressure. `generate()` produces random values in normal Mars ranges 90% of the time (temp -80 to 30°C, methane 0-0.05 ppm, radiation 0-100 μSv/h). 10% of the time it injects anomalous values (temp 55-120, methane 0.12-0.50, radiation 220-500) to ensure ML models trigger during demos. Goroutine exits cleanly when `done` channel is closed.

#### `internal/httpclient/client.go`
Package `httpclient`. Exports `AnomalyResult` struct matching Python response contract: `is_anomaly` (bool), `confidence`, `weighted_score` (float64), `triggered_models` ([]string), `timestamp` (string). `Client` wraps `http.Client` with 2-second timeout — if Python server doesn't respond in 2s, the call fails and pipeline continues. `New(endpoint string)` constructor. `Predict(SensorData)` does JSON marshal → POST to `http://localhost:5050/predict` → JSON decode response. On any failure (timeout, connection refused, non-200 status), returns error. Caller (main.go) logs and skips — pipeline never blocks.

#### `internal/mqttpub/pub.go`
Package `mqttpub`. Defines `TelemetryPayload`, `SensorPayload`, `AnomalyPayload` structs matching the final MQTT JSON contract for Unity: `{"sensor":{...}, "anomaly":{...}, "timestamp":"..."}`. `Publisher` wraps paho MQTT client. `New(brokerURL string)` creates client with auto-reconnect enabled, connect retry enabled (2s interval), unique client ID via unix nano. Connection is non-blocking — uses `ConnectRetry` so `Connect()` returns immediately and retries in the background. If broker is down at startup, logs a warning and continues; publishes will work once broker comes online. `Publish(SensorData, *AnomalyResult)` builds final payload, marshals to JSON, publishes to topic `rover/telemetry` with QoS 1 and 2s publish timeout. `Close()` disconnects with 1s quiesce.

**Fix applied during testing:** Original implementation used `WaitTimeout(5s)` on connect which blocked indefinitely when `ConnectRetry` was true and broker was down. Changed to best-effort 3s wait with background retry — startup no longer hangs.

#### `cmd/main.go`
Package `main`. Entry point that wires the full pipeline: `generator.Start(done)` → goroutine reads from sensor channel → `mlClient.Predict(data)` → on error: log + skip + continue → on success: log anomalies → `pub.Publish(data, result)`. Uses `os.Signal` (SIGINT, SIGTERM) for graceful shutdown — closes `done` channel which stops the generator ticker and goroutine. Log flags include microsecond timestamps.

### Infrastructure

#### `docker-compose.yml`
Single service: `eclipse-mosquitto:2`. Ports: `1883:1883` (MQTT), `9001:9001` (WebSocket for Unity). Volume mounts local `mosquitto/mosquitto.conf`. No `version` field (deprecated in modern Docker Compose).

#### `mosquitto/mosquitto.conf`
Two listeners: port 1883 (default MQTT protocol), port 9001 (WebSocket protocol for Unity). Anonymous access enabled (`allow_anonymous true`).

#### `.gitignore`
Covers all 4 stack layers: Go binaries/vendor, Python __pycache__/venv/trained .joblib models, Unity Library/Temp/Build/solution files, Docker Mosquitto data/log volumes, IDE files (.idea/.vscode), OS files (.DS_Store).

## Current Project State

Python ML side (`anomaly-ml-python/`) was built separately by another team member. Contains `train.py`, `inference.py`, `server.py`, `requirements.txt`, and `models/` directory. Unity side (`unity-dashboard/`) not yet created.

## Verification Results

- `go vet ./...` — clean, no issues
- `go build ./...` — compiles successfully
- Live run test: sensor generation at 10Hz confirmed, HTTP client gracefully handles connection refused (logs + skips), MQTT auto-reconnects in background, graceful shutdown via SIGTERM works (exit 143 = 128+15)

## Data Flow When All Services Running

```
generator (10Hz) → channel → main goroutine → HTTP POST /predict → Python returns AnomalyResult → MQTT publish "rover/telemetry" → Unity subscribes and renders
```

## JSON Contracts (immutable)

Go→Python: `{"temperature":23.4,"methane_level":0.012,"radiation":55.2,"timestamp":"2025-01-01T12:00:00Z"}`

Python→Go: `{"is_anomaly":true,"confidence":0.83,"weighted_score":0.76,"triggered_models":["isolation_forest","lof"],"timestamp":"2025-01-01T12:00:00Z"}`

Go→MQTT→Unity: `{"sensor":{"temperature":23.4,"methane_level":0.012,"radiation":55.2},"anomaly":{"is_anomaly":true,"confidence":0.83,"weighted_score":0.76,"triggered_models":["isolation_forest","lof"]},"timestamp":"2025-01-01T12:00:00Z"}`
