package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

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
	req := httptest.NewRequest(http.MethodGet, "/stats", nil)
	w := httptest.NewRecorder()
	statsHandler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}

	var stats Stats
	json.NewDecoder(w.Body).Decode(&stats)

	if stats.TotalProcessed < 0 {
		t.Fatal("total_processed should be >= 0")
	}
}
