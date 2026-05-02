package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

func resetProcessedEvents() {
	mu.Lock()
	processedEvents = nil
	mu.Unlock()
}

func TestHealthHandler(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	w := httptest.NewRecorder()
	healthHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var resp map[string]interface{}
	json.NewDecoder(w.Body).Decode(&resp)

	if resp["status"] != "healthy" {
		t.Fatalf("expected healthy, got %v", resp["status"])
	}
	if resp["service"] != "processor" {
		t.Fatalf("expected processor, got %v", resp["service"])
	}
}

func TestProcessHandler_Success(t *testing.T) {
	resetProcessedEvents()

	event := Event{
		ID:      "test-123",
		Type:    "user.signup",
		Payload: map[string]interface{}{"user": "alice"},
	}
	body, _ := json.Marshal(event)
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
	w := httptest.NewRecorder()
	processHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var result ProcessResult
	json.NewDecoder(w.Body).Decode(&result)

	if result.EventID != "test-123" {
		t.Fatalf("expected event_id test-123, got %s", result.EventID)
	}
	if result.Priority != "medium" {
		t.Fatalf("expected priority medium for signup, got %s", result.Priority)
	}
}

func TestProcessHandler_HighPriority(t *testing.T) {
	resetProcessedEvents()

	event := Event{ID: "err-1", Type: "system.error"}
	body, _ := json.Marshal(event)
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
	w := httptest.NewRecorder()
	processHandler(w, req)

	var result ProcessResult
	json.NewDecoder(w.Body).Decode(&result)

	if result.Priority != "high" {
		t.Fatalf("expected high priority for error event, got %s", result.Priority)
	}
}

func TestProcessHandler_LowPriority(t *testing.T) {
	resetProcessedEvents()

	event := Event{ID: "info-1", Type: "system.info"}
	body, _ := json.Marshal(event)
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
	w := httptest.NewRecorder()
	processHandler(w, req)

	var result ProcessResult
	json.NewDecoder(w.Body).Decode(&result)

	if result.Priority != "low" {
		t.Fatalf("expected low priority, got %s", result.Priority)
	}
}

func TestProcessHandler_InvalidJSON(t *testing.T) {
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader([]byte("not json")))
	w := httptest.NewRecorder()
	processHandler(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestProcessHandler_MissingFields(t *testing.T) {
	body, _ := json.Marshal(map[string]string{"id": "x"})
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
	w := httptest.NewRecorder()
	processHandler(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing type, got %d", w.Code)
	}
}

func TestProcessHandler_MethodNotAllowed(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/process", nil)
	w := httptest.NewRecorder()
	processHandler(w, req)

	if w.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", w.Code)
	}
}

func TestGenerateTags(t *testing.T) {
	event := Event{
		Type:    "user.signup",
		Payload: map[string]interface{}{"key": "value"},
	}
	tags := generateTags(event)

	found := map[string]bool{}
	for _, tag := range tags {
		found[tag] = true
	}

	if !found["user"] || !found["signup"] {
		t.Fatalf("expected tags to contain type parts, got %v", tags)
	}
	if !found["has-payload"] {
		t.Fatalf("expected has-payload tag, got %v", tags)
	}
}

func TestClassifyPriority(t *testing.T) {
	tests := []struct {
		eventType string
		expected  string
	}{
		{"system.error", "high"},
		{"app.alert", "high"},
		{"disk.warning", "medium"},
		{"user.signup", "medium"},
		{"page.view", "low"},
	}

	for _, tt := range tests {
		got := classifyPriority(tt.eventType)
		if got != tt.expected {
			t.Errorf("classifyPriority(%q) = %q, want %q", tt.eventType, got, tt.expected)
		}
	}
}

func TestStatsHandler(t *testing.T) {
	resetProcessedEvents()

	req := httptest.NewRequest(http.MethodGet, "/stats", nil)
	w := httptest.NewRecorder()
	statsHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var stats Stats
	json.NewDecoder(w.Body).Decode(&stats)

	if stats.TotalProcessed != 0 {
		t.Fatalf("expected 0 total_processed after reset, got %d", stats.TotalProcessed)
	}
}

func TestStatsHandler_AfterProcessing(t *testing.T) {
	resetProcessedEvents()

	events := []Event{
		{ID: "e1", Type: "system.error", Payload: map[string]interface{}{"k": "v"}},
		{ID: "e2", Type: "user.signup"},
		{ID: "e3", Type: "page.view"},
	}

	for _, event := range events {
		body, _ := json.Marshal(event)
		req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
		w := httptest.NewRecorder()
		processHandler(w, req)
		if w.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", w.Code)
		}
	}

	req := httptest.NewRequest(http.MethodGet, "/stats", nil)
	w := httptest.NewRecorder()
	statsHandler(w, req)

	var stats Stats
	json.NewDecoder(w.Body).Decode(&stats)

	if stats.TotalProcessed != 3 {
		t.Fatalf("expected 3 total_processed, got %d", stats.TotalProcessed)
	}
	if stats.ByPriority["high"] != 1 {
		t.Errorf("expected 1 high priority, got %d", stats.ByPriority["high"])
	}
	if stats.ByPriority["medium"] != 1 {
		t.Errorf("expected 1 medium priority, got %d", stats.ByPriority["medium"])
	}
	if stats.ByPriority["low"] != 1 {
		t.Errorf("expected 1 low priority, got %d", stats.ByPriority["low"])
	}
}

func TestProcessedHandler(t *testing.T) {
	resetProcessedEvents()

	event := Event{ID: "ph-1", Type: "user.login"}
	body, _ := json.Marshal(event)
	req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
	w := httptest.NewRecorder()
	processHandler(w, req)

	req = httptest.NewRequest(http.MethodGet, "/processed", nil)
	w = httptest.NewRecorder()
	processedHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var results []ProcessResult
	json.NewDecoder(w.Body).Decode(&results)

	if len(results) != 1 {
		t.Fatalf("expected 1 result, got %d", len(results))
	}
	if results[0].EventID != "ph-1" {
		t.Errorf("expected event_id ph-1, got %s", results[0].EventID)
	}
}

func TestProcessedEvents_MaxCapacity(t *testing.T) {
	resetProcessedEvents()
	oldMax := maxProcessed
	maxProcessed = 3
	defer func() { maxProcessed = oldMax }()

	for i := 0; i < 5; i++ {
		event := Event{ID: fmt.Sprintf("cap-%d", i), Type: "test.event"}
		body, _ := json.Marshal(event)
		req := httptest.NewRequest(http.MethodPost, "/process", bytes.NewReader(body))
		w := httptest.NewRecorder()
		processHandler(w, req)
	}

	req := httptest.NewRequest(http.MethodGet, "/processed", nil)
	w := httptest.NewRecorder()
	processedHandler(w, req)

	var results []ProcessResult
	json.NewDecoder(w.Body).Decode(&results)

	if len(results) != 3 {
		t.Fatalf("expected 3 results (capped), got %d", len(results))
	}
	if results[0].EventID != "cap-2" {
		t.Errorf("expected oldest remaining to be cap-2, got %s", results[0].EventID)
	}
	if results[2].EventID != "cap-4" {
		t.Errorf("expected newest to be cap-4, got %s", results[2].EventID)
	}
}
