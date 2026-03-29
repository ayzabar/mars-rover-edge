# 🚀 Mars Rover Edge Computing & Anomaly Detection

![Go](https://img.shields.io/badge/Go-1.22+-00ADD8?style=flat&logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?style=flat&logo=eclipsemosquitto&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?style=flat&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)
![Event](https://img.shields.io/badge/TUA-Astro%20Hackathon-red?style=flat)

> Real-time edge computing simulation on a Mars Rover — sensor fusion, on-device ML anomaly detection, and dual mission control dashboards with simulated Mars→Earth transmission delay.

---

## 🛰️ What Is This?

A Mars Rover generates temperature, methane, and radiation readings at **10Hz**. Instead of blindly streaming everything to Earth (physically impossible at 3–22 minute signal delay), the rover processes data **locally at the edge** using a 3-model ML ensemble. Only anomalies are relayed to Earth — with a simulated 18-second transmission delay.

Two dashboards visualize the system:
- **Rover HUD** (`dashboard.html`) — onboard realtime view, 10Hz raw feed
- **JPL Mission Control** (`earth_dashboard.html`) — Earth-side, anomaly alerts only, 18s delayed

---

## 🧠 How Anomaly Detection Works

Three models run in parallel on every sensor reading. Results are combined via weighted voting:

```
weighted_score = (Isolation Forest × 0.5)
              + (Local Outlier Factor × 0.3)
              + (Z-Score × 0.2)

if weighted_score > 0.5 → ANOMALY
```

| Model | Weight | What It Catches |
|---|---|---|
| Isolation Forest | 50% | Global outliers — values far from any cluster |
| Local Outlier Factor | 30% | Local density anomalies — unusual neighborhoods |
| Z-Score | 20% | Statistical spikes — breach of 2.5σ threshold |

Each model independently flags anomalies. The weighted sum determines the final verdict — reducing false positives that a single model would produce.

---

## 📡 Architecture

```
┌─────────────────────────────────────────────────────┐
│                  MARS ROVER (EDGE)                  │
│                                                     │
│  [sensor.go] ──10Hz──▶ [client.go] ──HTTP POST──▶  │
│                              │       localhost:5050  │
│                              ▼                      │
│                    [Python Flask ML]                │
│                    IF + LOF + Z-Score               │
│                    weighted ensemble                │
│                              │                      │
│                    AnomalyResult returned           │
│                              ▼                      │
│  [pub.go] ──MQTT──▶ Mosquitto Broker               │
│                              │                      │
└──────────────────────────────┼──────────────────────┘
                               │
              ┌────────────────┴─────────────────┐
              ▼                                  ▼
   rover/telemetry (10Hz)           earth/alerts (anomaly only)
   every reading, no delay          18 second delay →
              │                                  │
              ▼                                  ▼
     dashboard.html                  earth_dashboard.html
     Rover Onboard HUD               JPL Mission Control
```

---

## 🌍 Data Sources

Sensor ranges are based on **real NASA Curiosity REMS** (Rover Environmental Monitoring Station) measurements:

| Sensor | Normal Range | Anomaly Threshold | Source |
|---|---|---|---|
| Temperature | −90°C to +30°C | > 40°C or < −110°C | REMS air/ground sensor |
| Radiation | 180–280 μSv/h | > 500 μSv/h | RAD instrument |
| Methane | 0.3–0.7 ppb | > 1.5 ppb | TLS spectrometer |

The ML models are trained on synthetic data generated within these real-world bounds. Anomaly injection uses **single-fault patterns** — only one sensor spikes at a time, matching realistic hardware failure signatures.

Reference: [NASA PDS REMS Data](https://pds-geosciences.wustl.edu/missions/msl/rems.htm)

---

## ⚡ Tech Stack

| Layer | Technology |
|---|---|
| Sensor generation & orchestration | Go 1.22+, goroutines, channels |
| ML inference server | Python 3.10+, Flask, scikit-learn, joblib |
| Message broker | Eclipse Mosquitto (Docker) |
| Dashboards | HTML/CSS/JS, Chart.js, MQTT.js |
| Containerization | Docker, docker-compose |

---

## 📂 Directory Structure

```
mars-rover-edge/
├── edge-core-go/
│   ├── cmd/main.go                  # Entry point, pipeline orchestration
│   └── internal/
│       ├── generator/sensor.go      # 10Hz sensor data generation
│       ├── httpclient/client.go     # HTTP POST to Python /predict
│       └── mqttpub/pub.go           # MQTT publish (rover + earth topics)
├── anomaly-ml-python/
│   ├── train.py                     # One-shot model training
│   ├── inference.py                 # Weighted voting ensemble
│   ├── server.py                    # Flask inference server (:5050)
│   └── models/ensemble.joblib       # Trained frozen models (4MB)
├── dashboard.html                   # Rover onboard HUD
├── earth_dashboard.html             # JPL Earth mission control
├── chart.min.js                     # Chart.js (vendored)
├── mqtt.min.js                      # MQTT browser client (vendored)
├── docker-compose.yml               # Mosquitto broker
├── mosquitto/mosquitto.conf
└── docs/
    └── CONTEXT.md                   # Full architecture reference
```

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-repo/mars-rover-edge.git
cd mars-rover-edge

# 2. Start MQTT broker
docker-compose up -d

# 3. Train the ML model (one time only)
cd anomaly-ml-python
pip install -r requirements.txt
python train.py

# 4. Start the inference server
python server.py

# 5. Start the Go edge core (new terminal)
cd edge-core-go
go run cmd/main.go

# 6. Open dashboards in browser
open dashboard.html          # Rover HUD — realtime 10Hz
open earth_dashboard.html    # JPL Mission Control — anomaly alerts
```

> Both dashboards fall back to **simulation mode** automatically if the MQTT broker is unavailable — always demo-ready.

---

## 👨‍🚀 Team

| Name |
|---|
| Bahri Ayzabar |
| Sabri Gür |
| Mehmet Ali Dönmez |
| Yoldaş Çiçekli |
| Oğuzhan Işık |

---

> Built in 24 hours at **TUA Astro Hackathon** — Turkish Space Agency.
