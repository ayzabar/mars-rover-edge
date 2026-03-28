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
// Ranges match NASA REMS real data used to retrain the Python ML model.
// ~10% of the time it injects anomalous values to trigger ML detection during demos.
func generate() SensorData {
	d := SensorData{
		Timestamp: time.Now().UTC(),
	}

	if rand.Float64() < 0.10 { // ~10% anomaly injection
		// Anomaly ranges — clearly outside the normal NASA REMS envelope
		switch rand.Intn(3) {
		case 0: // High temperature anomaly
			d.Temperature = randomRange(45.0, 95.0)    // normal max +30 °C
			d.MethaneLevel = randomRange(0.3, 0.7)      // normal
			d.Radiation = randomRange(180.0, 280.0)     // normal
		case 1: // Methane spike anomaly
			d.Temperature = randomRange(-90.0, 30.0)    // normal
			d.MethaneLevel = randomRange(1.5, 3.0)      // anomaly: >1.5 ppb
			d.Radiation = randomRange(180.0, 280.0)     // normal
		case 2: // Radiation spike anomaly (solar flare)
			d.Temperature = randomRange(-90.0, 30.0)    // normal
			d.MethaneLevel = randomRange(0.3, 0.7)      // normal
			d.Radiation = randomRange(500.0, 900.0)     // anomaly: >500 μSv/h
		}
	} else {
		// Normal ranges — NASA REMS real data envelope
		d.Temperature = randomRange(-90.0, 30.0)   // °C
		d.MethaneLevel = randomRange(0.3, 0.7)     // ppb
		d.Radiation = randomRange(180.0, 280.0)    // μSv/h
	}

	return d
}

func randomRange(min, max float64) float64 {
	return min + rand.Float64()*(max-min)
}
