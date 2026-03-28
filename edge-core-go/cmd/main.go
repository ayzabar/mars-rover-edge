package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"edge-core-go/internal/generator"
	"edge-core-go/internal/httpclient"
	"edge-core-go/internal/mqttpub"
)

const (
	mlEndpoint = "http://localhost:5050/predict"
	mqttBroker = "tcp://localhost:1883"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	log.Println("[MAIN] Mars Rover Edge Core starting...")

	// --- MQTT Publisher ---
	pub, err := mqttpub.New(mqttBroker)
	if err != nil {
		log.Fatalf("[MAIN] MQTT publisher init failed: %v", err)
	}
	defer pub.Close()

	// --- HTTP Client for Python ML server ---
	mlClient := httpclient.New(mlEndpoint)

	// --- Graceful shutdown ---
	done := make(chan struct{})
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	// --- Sensor generator (10 Hz) ---
	sensorCh := generator.Start(done)

	log.Println("[MAIN] Pipeline running — generator → ML predict → MQTT publish")
	log.Println("[MAIN] Press Ctrl+C to stop")

	// --- Main processing loop ---
	go func() {
		for data := range sensorCh {
			// 1. Send to Python ML server
			result, err := mlClient.Predict(data)
			if err != nil {
				log.Printf("[HTTP] ML predict failed (skipping): %v", err)
				continue
			}

			// 2. Log anomalies
			if result.IsAnomaly {
				log.Printf("[ANOMALY] temp=%.1f methane=%.4f rad=%.1f | confidence=%.2f score=%.2f models=%v",
					data.Temperature, data.MethaneLevel, data.Radiation,
					result.Confidence, result.WeightedScore, result.TriggeredModels)
			}

			// 3. Publish to MQTT
			if err := pub.Publish(data, result); err != nil {
				log.Printf("[MQTT] publish failed: %v", err)
			}
		}
	}()

	// --- Wait for shutdown signal ---
	sig := <-sigCh
	log.Printf("[MAIN] received signal %v, shutting down...", sig)
	close(done)
	log.Println("[MAIN] shutdown complete")
}
