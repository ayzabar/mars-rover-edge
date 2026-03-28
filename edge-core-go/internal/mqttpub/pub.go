package mqttpub

import (
	"encoding/json"
	"fmt"
	"log"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"

	"edge-core-go/internal/generator"
	"edge-core-go/internal/httpclient"
)

const (
	defaultTopic = "rover/telemetry"
	qos          = 1
)

// TelemetryPayload is the final MQTT message published to the broker for Unity to consume.
// Matches the JSON contract exactly.
type TelemetryPayload struct {
	Sensor  SensorPayload  `json:"sensor"`
	Anomaly AnomalyPayload `json:"anomaly"`
	// Timestamp as RFC3339 string at the top level.
	Timestamp string `json:"timestamp"`
}

// SensorPayload is the sensor portion of the telemetry payload (no timestamp).
type SensorPayload struct {
	Temperature  float64 `json:"temperature"`
	MethaneLevel float64 `json:"methane_level"`
	Radiation    float64 `json:"radiation"`
}

// AnomalyPayload is the anomaly portion of the telemetry payload (no timestamp).
type AnomalyPayload struct {
	IsAnomaly       bool     `json:"is_anomaly"`
	Confidence      float64  `json:"confidence"`
	WeightedScore   float64  `json:"weighted_score"`
	TriggeredModels []string `json:"triggered_models"`
}

// Publisher publishes combined sensor + anomaly data to an MQTT broker.
type Publisher struct {
	client mqtt.Client
	topic  string
}

// New creates and connects an MQTT publisher.
func New(brokerURL string) (*Publisher, error) {
	opts := mqtt.NewClientOptions().
		AddBroker(brokerURL).
		SetClientID(fmt.Sprintf("mars-rover-edge-%d", time.Now().UnixNano())).
		SetAutoReconnect(true).
		SetConnectRetry(true).
		SetConnectRetryInterval(2 * time.Second).
		SetConnectionLostHandler(func(_ mqtt.Client, err error) {
			log.Printf("[MQTT] connection lost: %v", err)
		}).
		SetOnConnectHandler(func(_ mqtt.Client) {
			log.Println("[MQTT] connected to broker")
		})

	client := mqtt.NewClient(opts)
	// Connect is non-blocking with ConnectRetry — it will keep trying in the background.
	// This lets the pipeline start immediately even if the broker isn't up yet.
	token := client.Connect()
	token.WaitTimeout(3 * time.Second) // best-effort initial connect
	if token.Error() != nil {
		log.Printf("[MQTT] initial connect failed (%v), will keep retrying in background", token.Error())
	}

	return &Publisher{
		client: client,
		topic:  defaultTopic,
	}, nil
}

// Publish builds the final telemetry JSON from sensor data + anomaly result and publishes it.
func (p *Publisher) Publish(sensor generator.SensorData, anomaly *httpclient.AnomalyResult) error {
	payload := TelemetryPayload{
		Sensor: SensorPayload{
			Temperature:  sensor.Temperature,
			MethaneLevel: sensor.MethaneLevel,
			Radiation:    sensor.Radiation,
		},
		Anomaly: AnomalyPayload{
			IsAnomaly:       anomaly.IsAnomaly,
			Confidence:      anomaly.Confidence,
			WeightedScore:   anomaly.WeightedScore,
			TriggeredModels: anomaly.TriggeredModels,
		},
		Timestamp: sensor.Timestamp.Format(time.RFC3339),
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("json marshal payload: %w", err)
	}

	token := p.client.Publish(p.topic, qos, false, data)
	if !token.WaitTimeout(2 * time.Second) {
		return fmt.Errorf("mqtt publish timeout")
	}
	return token.Error()
}

// Close disconnects from the MQTT broker gracefully.
func (p *Publisher) Close() {
	p.client.Disconnect(1000)
	log.Println("[MQTT] disconnected")
}
