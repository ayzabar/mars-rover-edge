package httpclient

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"edge-core-go/internal/generator"
)

// AnomalyResult is the response from the Python ML server. Matches the JSON contract exactly.
type AnomalyResult struct {
	IsAnomaly       bool     `json:"is_anomaly"`
	Confidence      float64  `json:"confidence"`
	WeightedScore   float64  `json:"weighted_score"`
	TriggeredModels []string `json:"triggered_models"`
	Timestamp       string   `json:"timestamp"`
}

// Client sends sensor data to the Python ML inference server via HTTP POST.
type Client struct {
	httpClient *http.Client
	endpoint   string
}

// New creates an HTTP client targeting the given prediction endpoint.
func New(endpoint string) *Client {
	return &Client{
		httpClient: &http.Client{
			Timeout: 2 * time.Second,
		},
		endpoint: endpoint,
	}
}

// Predict sends sensor data to the ML server and returns the anomaly result.
// Returns an error if the server is unreachable or returns a non-200 status.
func (c *Client) Predict(data generator.SensorData) (*AnomalyResult, error) {
	body, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("json marshal: %w", err)
	}

	resp, err := c.httpClient.Post(c.endpoint, "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("http post: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("ml server returned %d: %s", resp.StatusCode, string(respBody))
	}

	var result AnomalyResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("json decode: %w", err)
	}

	return &result, nil
}
