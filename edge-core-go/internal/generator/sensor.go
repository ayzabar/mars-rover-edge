package generator

import (
	"math/rand"
	"time"
)

// SensorData matches the JSON contract expected by Python ML server and Unity dashboard.
type SensorData struct {
	Temperature  float64   `json:"temperature"`
	MethaneLevel float64   `json:"methane_level"`
	Radiation    float64   `json:"radiation"`
	Timestamp    time.Time `json:"timestamp"`
}

// Start begins generating sensor readings at 10 Hz (every 100ms) and sends them
// on the returned channel. It stops when the done channel is closed.
func Start(done <-chan struct{}) <-chan SensorData {
	ch := make(chan SensorData, 64)

	go func() {
		defer close(ch)
		ticker := time.NewTicker(100 * time.Millisecond) // 10 Hz
		defer ticker.Stop()

		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				data := generate()
				select {
				case ch <- data:
				case <-done:
					return
				}
			}
		}
	}()

	return ch
}

// generate produces a single SensorData reading.
// ~10% of the time it injects anomalous values to trigger ML detection during demos.
func generate() SensorData {
	d := SensorData{
		Timestamp: time.Now().UTC(),
	}

	if rand.Float64() < 0.10 { // ~10% anomaly injection
		d.Temperature = randomRange(55, 120)     // normal max is 30, anomaly >50
		d.MethaneLevel = randomRange(0.12, 0.50)  // normal max 0.05, anomaly >0.1
		d.Radiation = randomRange(220, 500)        // normal max 100, anomaly >200
	} else {
		d.Temperature = randomRange(-80, 30)
		d.MethaneLevel = randomRange(0.0, 0.05)
		d.Radiation = randomRange(0, 100)
	}

	return d
}

func randomRange(min, max float64) float64 {
	return min + rand.Float64()*(max-min)
}
