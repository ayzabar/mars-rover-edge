
# 🚀 MARS ROVER EDGE COMPUTING — MASTER CONTEXT

> **READ THIS FIRST.** Bu dosya tüm takım üyeleri için tek gerçek kaynaktır.  
> Geliştirmeye başlamadan önce tamamını oku. Sonra kendi alanına odaklan.

---

## 📌 PROJE ÖZETİ

Düşük kaynaklı bir Mars Rover'ı üzerinde **edge computing simülasyonu**.  
Rover sensör verisi üretir → 3 ML modeli anomali tespiti yapar → Unity 3D dashboard'a uyarı iletir.

**Hikaye:** Rover, Mars yüzeyinde gezerken sıcaklık, metan ve radyasyon değerlerini 10Hz'de ölçer. Anormal değerler tespit edilince Unity dashboard kırmızı alarm verir.

---

## 🛠 TEKNOLOJİ STACK'İ

| Katman | Teknoloji | Neden |
|---|---|---|
| Sensör Üretimi & Orkestrasyon | **Go 1.22+** | Goroutine'ler, hafif, hızlı |
| ML Inference Sunucusu | **Python 3.10+ (Flask)** | Basit HTTP, sıfır codegen |
| Mesaj Kuyruğu | **Eclipse Mosquitto (Docker)** | Hafif MQTT broker |
| Dashboard | **Unity3D (C#, M2Mqtt)** | Takımda game dev var |
| Container | **Docker + docker-compose** | Tek komutla ayağa kalkar |

> ❌ **gRPC / Protobuf KULLANMIYORUZ.** Go ↔ Python arası iletişim saf **HTTP/JSON REST** ile yapılıyor. Aynı mimari, sıfır acı.

---

## 📂 KLASÖR YAPISI

```
mars-rover-edge/
├── docs/
│   └── CONTEXT.md                   # Bu dosya
├── edge-core-go/                    # Go Backend — SEN BURAYI GELİŞTİRİYORSAN bak: §GO
│   ├── cmd/
│   │   └── main.go                  # Entry point
│   ├── internal/
│   │   ├── generator/
│   │   │   └── sensor.go            # Sensör verisi üretimi (10Hz)
│   │   ├── httpclient/
│   │   │   └── client.go            # Python'a HTTP POST
│   │   └── mqttpub/
│   │       └── pub.go               # MQTT'ye publish
│   └── go.mod
├── anomaly-ml-python/               # Python ML — SEN BURAYI GELİŞTİRİYORSAN bak: §PYTHON
│   ├── models/
│   │   └── ensemble.joblib          # Eğitilmiş frozen modeller
│   ├── train.py                     # Tek seferlik eğitim scripti
│   ├── server.py                    # Flask HTTP sunucusu (:5050)
│   ├── inference.py                 # Weighted voting mantığı
│   └── requirements.txt
├── unity-dashboard/                 # Unity — SEN BURAYI GELİŞTİRİYORSAN bak: §UNITY
│   └── Assets/Scripts/
│       ├── MqttReceiver.cs          # MQTT subscribe + JSON parse
│       └── RoverManager.cs          # Görsel state yönetimi
└── docker-compose.yml               # Mosquitto broker config
```

---

## 🔄 VERİ AKIŞI (Uçtan Uca)

```
[Go: sensor.go]
    ↓  10Hz'de SensorData üretir { temperature, methane_level, radiation, timestamp }

[Go: client.go]
    ↓  JSON serialize eder
    ↓  HTTP POST → http://localhost:5050/predict

[Python: server.py + inference.py]
    ↓  JSON deserialize eder
    ↓  3 modelden weighted vote çalıştırır
    ↓  AnomalyResult döner { is_anomaly, confidence, weighted_score, triggered_models }

[Go: pub.go]
    ↓  SensorData + AnomalyResult birleştirir
    ↓  Final JSON payload oluşturur
    ↓  Mosquitto MQTT broker'a publish eder → topic: "rover/telemetry"

[Unity: MqttReceiver.cs]
    ↓  "rover/telemetry" topic'ini dinler
    ↓  is_anomaly == true ise → RoverManager.cs kırmızı alarm tetikler
```

---

## 📜 JSON KONTRATLAR (Değişmez — Herkes Buna Uyar)

### 1. Go → Python (`POST /predict`)

```json
{
  "temperature": 23.4,
  "methane_level": 0.012,
  "radiation": 55.2,
  "timestamp": "2025-01-01T12:00:00Z"
}
```

### 2. Python → Go (Response)

```json
{
  "is_anomaly": true,
  "confidence": 0.83,
  "weighted_score": 0.76,
  "triggered_models": ["isolation_forest", "lof"],
  "timestamp": "2025-01-01T12:00:00Z"
}
```

### 3. Go → Mosquitto → Unity (Final MQTT Payload)

```json
{
  "sensor": {
    "temperature": 23.4,
    "methane_level": 0.012,
    "radiation": 55.2
  },
  "anomaly": {
    "is_anomaly": true,
    "confidence": 0.83,
    "weighted_score": 0.76,
    "triggered_models": ["isolation_forest", "lof"]
  },
  "timestamp": "2025-01-01T12:00:00Z"
}
```

> ⚠️ **Bu kontratları kimse tek taraflı değiştirmez.** Değişiklik gerekirse tüm takım bilgilendirilir.

---

## 🧠 ML MODELLERİ — WEIGHTED VOTING ENSEMBLE

3 model paralel çalışır, sonuçları ağırlıklı toplanır:

| Model | Ağırlık | Mantık |
|---|---|---|
| **Isolation Forest** | %50 | Path length anomaly isolation |
| **LOF** (Local Outlier Factor) | %30 | Yerel yoğunluk sapması |
| **Z-Score** | %20 | `Z = (X - μ) / σ` |

```
weighted_score = (IF_result × 0.5) + (LOF_result × 0.3) + (zscore_result × 0.2)
if weighted_score > threshold:
    is_anomaly = True
```

- Modeller `train.py` ile **sentetik Mars verisi** üzerinde eğitilir.
- `ensemble.joblib` olarak kaydedilir.
- Runtime'da **sadece inference** — yeniden eğitim yok.

---

## 🌡️ SENSÖR VERİSİ — DEĞER ARALIKLARI

| Sensör | Normal Aralık | Anomali Tetikleyici |
|---|---|---|
| `temperature` (°C) | -80 ile +30 | > 50 veya < -100 |
| `methane_level` (ppm) | 0.0 ile 0.05 | > 0.1 |
| `radiation` (μSv/h) | 0 ile 100 | > 200 |

---

## ⚙️ SERVİS PORT'LARI & BAĞLANTI BİLGİLERİ

| Servis | Port | Protokol |
|---|---|---|
| Python Flask ML Server | `5050` | HTTP |
| Mosquitto MQTT Broker | `1883` | MQTT |
| MQTT WebSocket (Unity için) | `9001` | WS |

---

## 🐳 DOCKER (Mosquitto)

`docker-compose.yml` sadece Mosquitto'yu ayağa kaldırır:

```yaml
version: '3.8'
services:
  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
      - "9001:9001"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
```

`mosquitto.conf`:
```
listener 1883
listener 9001
protocol websockets
allow_anonymous true
```

---

## 🚀 HIZLI BAŞLATMA (Herşeyi ayağa kaldırmak için)

```bash
# Terminal 1 — MQTT Broker
docker-compose up

# Terminal 2 — Python ML Sunucusu
cd anomaly-ml-python
pip install -r requirements.txt
python train.py        # SADECE BİR KERE — modeli eğitip kaydeder
python server.py       # Flask :5050'de başlar

# Terminal 3 — Go Backend
cd edge-core-go
go mod tidy
go run cmd/main.go     # Sensör üretimi + HTTP client + MQTT publish başlar
```

---

---

# 👤 ALANA ÖZEL KILAVUZLAR

---

## § GO — Edge Core Backend Geliştiricisi

**Senin sorumluluğun:** Tüm Go backend. 3 dosya yazacaksın + main.go.

### `internal/generator/sensor.go`

```go
// SensorData struct — Python ve Unity bu struct'ı bekliyor, değiştirme
type SensorData struct {
    Temperature   float64   `json:"temperature"`
    MethaneLevel  float64   `json:"methane_level"`
    Radiation     float64   `json:"radiation"`
    Timestamp     time.Time `json:"timestamp"`
}
```

- `time.Ticker` ile **10Hz** (100ms) veri üret.
- Normal aralıklarda rastgele değer, ara sıra (% ~10 ihtimal) anomali değeri üret. Demo için şart.
- Bir `channel` üzerinden `client.go`'ya ilet.

### `internal/httpclient/client.go`

- `SensorData` → JSON serialize → `POST http://localhost:5050/predict`
- Response → `AnomalyResult` struct'a deserialize et.
- **Timeout koy:** 2 saniye. Python cevap vermezse skip et, logla, devam et. Pipeline durmamalı.

```go
type AnomalyResult struct {
    IsAnomaly       bool      `json:"is_anomaly"`
    Confidence      float64   `json:"confidence"`
    WeightedScore   float64   `json:"weighted_score"`
    TriggeredModels []string  `json:"triggered_models"`
    Timestamp       time.Time `json:"timestamp"`
}
```

### `internal/mqttpub/pub.go`

- `paho.mqtt.golang` paketi kullan.
- Broker: `tcp://localhost:1883`
- Topic: `rover/telemetry`
- `SensorData` + `AnomalyResult` → final JSON payload → publish.
- QoS 1 kullan.

### `cmd/main.go`

- Her şeyi wire et: generator → httpclient → mqttpub.
- Goroutine'ler arası `channel` kullan.
- Graceful shutdown için `os.Signal` yakala.

### `go.mod` Dependencies

```
github.com/eclipse/paho.mqtt.golang
```

---

## § PYTHON — ML Inference Geliştiricisi

**Senin sorumluluğun:** Eğitim scripti, inference mantığı ve Flask sunucusu.

### `train.py`

- **Sentetik Mars verisi üret:** `numpy` ile normal dağılımlı + anomali örnekler.
- 3 modeli eğit:
  - `IsolationForest(contamination=0.1)`
  - `LocalOutlierFactor(novelty=True, contamination=0.1)`
  - Z-Score için `mean` ve `std` hesapla, kaydet.
- Hepsini `joblib.dump()` ile `models/ensemble.joblib`'e kaydet.

### `inference.py`

```python
def predict(temperature, methane_level, radiation) -> dict:
    # 1. Modelleri yükle (ensemble.joblib)
    # 2. Feature vector oluştur: [temperature, methane_level, radiation]
    # 3. Her modelden binary sonuç al (1 = anomali, 0 = normal)
    # 4. Weighted vote:
    #    score = (IF * 0.5) + (LOF * 0.3) + (zscore * 0.2)
    # 5. score > 0.5 ise is_anomaly = True
    # 6. Dict döndür (JSON kontratına uy!)
```

### `server.py`

```python
from flask import Flask, request, jsonify
from inference import predict

app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict_endpoint():
    data = request.get_json()
    result = predict(
        data['temperature'],
        data['methane_level'],
        data['radiation']
    )
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050)
```

### `requirements.txt`

```
flask
scikit-learn
joblib
numpy
```

> ⚠️ **LOF'u `novelty=True` ile eğit** — yoksa inference sırasında `predict()` çağıramazsın, hata verir.

---

## § UNITY — Dashboard Geliştiricisi

**Senin sorumluluğun:** MQTT'yi dinle, JSON parse et, görsel state yönet.

### Setup

- **M2Mqtt paketi** Unity'ye import et: `M2Mqtt.dll` Assets/Plugins/ altına koy.
- MQTT Broker: `localhost`, port `1883`.
- Subscribe topic: `rover/telemetry`

### `MqttReceiver.cs` — Yapması Gerekenler

```csharp
// 1. Start()'ta broker'a bağlan ve "rover/telemetry"'e subscribe ol
// 2. MqttClient.MqttMsgPublishReceived event'ini dinle
// 3. Gelen byte[] → UTF8 string → JSON parse (JsonUtility veya Newtonsoft)
// 4. TelemetryPayload nesnesine deserialize et
// 5. RoverManager.cs'e ilet

[Serializable]
public class SensorData {
    public float temperature;
    public float methane_level;
    public float radiation;
}

[Serializable]
public class AnomalyData {
    public bool is_anomaly;
    public float confidence;
    public float weighted_score;
    public string[] triggered_models;
}

[Serializable]
public class TelemetryPayload {
    public SensorData sensor;
    public AnomalyData anomaly;
    public string timestamp;
}
```

### `RoverManager.cs` — Yapması Gerekenler

```
is_anomaly == true  → Kırmızı ışık / alarm efekti aç
is_anomaly == false → Normal durum (yeşil/mavi)
confidence değeri  → UI'da göster (isteğe bağlı ama etkileyici görünür)
triggered_models   → Hangi model tetikledi → UI'da göster (jüri etkisi +++)
```

> ⚠️ **Unity ana thread'i:** MQTT callback'i ayrı thread'den gelir. `UnityMainThreadDispatcher` kullan veya bir bool flag + `Update()` döngüsü yöntemi uygula. Direkt UI güncellemeye çalışırsan crash yersin.

---

## ⚡ SAVAŞ PLANI (11.5 Saatlik Hackathon)

| # | Blok | Süre | Kim |
|---|---|---|---|
| 1 | Go: `sensor.go` + `client.go` + `main.go` | 2h | Go dev |
| 2 | Python: `train.py` + `inference.py` + `server.py` | 2.5h | ML dev |
| 3 | Go: `pub.go` + MQTT entegrasyon testi | 1.5h | Go dev |
| 4 | Unity: `MqttReceiver.cs` + `RoverManager.cs` | 3h | Game dev |
| 5 | Full integration test + bug fix | 1.5h | Herkes |
| 6 | Demo script + sunum hazırlığı | 1h | Herkes |

---

## 🔗 TEST SENARYOLARI (Integration için)

### Python'ı manual test et:

```bash
curl -X POST http://localhost:5050/predict \
  -H "Content-Type: application/json" \
  -d '{"temperature": 23.4, "methane_level": 0.012, "radiation": 55.2, "timestamp": "2025-01-01T12:00:00Z"}'
```

### MQTT'yi manual test et:

```bash
# Subscribe (başka terminalde çalıştır)
mosquitto_sub -h localhost -t "rover/telemetry"

# Publish test
mosquitto_pub -h localhost -t "rover/telemetry" -m '{"sensor":{"temperature":23.4},"anomaly":{"is_anomaly":true}}'
```

---

## ❓ SSS

**S: Go, Python'a bağlanamıyor.**  
C: `python server.py`'nin çalıştığından ve `localhost:5050`'de dinlediğinden emin ol. `curl` ile test et.

**S: MQTT mesajları gelmiyor.**  
C: `docker-compose up` çalışıyor mu? `mosquitto_sub` ile topic'i dinle, mesaj geliyor mu gör.

**S: Unity MQTT'ye bağlanamıyor.**  
C: Broker adresi `localhost` yerine makinenin LAN IP'si olmalı (Unity editörde çalışıyorsa sorun yok, build'de sorun çıkar).

**S: LOF `predict()` hatası veriyor.**  
C: `train.py`'de `novelty=True` ile eğittiğinden emin ol.

**S: Anomali hiç tetiklenmiyor.**  
C: `sensor.go`'da zaman zaman yüksek değer üret (sıcaklık > 50, radyasyon > 200). Demo için şart.

---

*Son güncelleme: Hackathon Gün 1 — Takım tarafından oluşturuldu.*
