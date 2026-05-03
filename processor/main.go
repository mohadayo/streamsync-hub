package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

type Event struct {
	ID        string                 `json:"id"`
	Type      string                 `json:"type"`
	Payload   map[string]interface{} `json:"payload"`
	Timestamp float64                `json:"timestamp"`
	Status    string                 `json:"status"`
}

type ProcessResult struct {
	EventID     string   `json:"event_id"`
	ProcessedAt float64  `json:"processed_at"`
	Tags        []string `json:"tags"`
	Priority    string   `json:"priority"`
	Summary     string   `json:"summary"`
}

type Stats struct {
	TotalProcessed int            `json:"total_processed"`
	ByPriority     map[string]int `json:"by_priority"`
	ByType         map[string]int `json:"by_type"`
}

var (
	processedEvents []ProcessResult
	mu              sync.Mutex
	logger          *log.Logger
	maxProcessed    int
	shutdownTimeout time.Duration
)

func init() {
	logger = log.New(os.Stdout, "[processor] ", log.LstdFlags)
	maxProcessed = 10000
	if v := os.Getenv("PROCESSOR_MAX_EVENTS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			maxProcessed = n
		}
	}
	shutdownTimeout = 30 * time.Second
	if v := os.Getenv("SHUTDOWN_TIMEOUT_SECONDS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			shutdownTimeout = time.Duration(n) * time.Second
		}
	}
}

func classifyPriority(eventType string) string {
	if strings.Contains(eventType, "error") || strings.Contains(eventType, "alert") {
		return "high"
	}
	if strings.Contains(eventType, "warning") || strings.Contains(eventType, "signup") {
		return "medium"
	}
	return "low"
}

func generateTags(event Event) []string {
	tags := []string{}
	parts := strings.Split(event.Type, ".")
	tags = append(tags, parts...)
	if len(event.Payload) > 0 {
		tags = append(tags, "has-payload")
	}
	return tags
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    "healthy",
		"service":   "processor",
		"timestamp": time.Now().Unix(),
	})
}

func processHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	var event Event
	if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
		logger.Printf("Failed to decode event: %v", err)
		http.Error(w, fmt.Sprintf(`{"error":"invalid JSON: %s"}`, err.Error()), http.StatusBadRequest)
		return
	}

	if event.ID == "" || event.Type == "" {
		logger.Println("Event missing id or type")
		http.Error(w, `{"error":"fields 'id' and 'type' are required"}`, http.StatusBadRequest)
		return
	}

	result := ProcessResult{
		EventID:     event.ID,
		ProcessedAt: float64(time.Now().UnixMilli()) / 1000.0,
		Tags:        generateTags(event),
		Priority:    classifyPriority(event.Type),
		Summary:     fmt.Sprintf("Processed event '%s' with priority '%s'", event.Type, classifyPriority(event.Type)),
	}

	mu.Lock()
	processedEvents = append(processedEvents, result)
	if len(processedEvents) > maxProcessed {
		removed := len(processedEvents) - maxProcessed
		processedEvents = processedEvents[removed:]
		logger.Printf("Evicted %d old events (store capped at %d)", removed, maxProcessed)
	}
	mu.Unlock()

	logger.Printf("Processed event: id=%s type=%s priority=%s", event.ID, event.Type, result.Priority)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func statsHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()

	stats := Stats{
		TotalProcessed: len(processedEvents),
		ByPriority:     make(map[string]int),
		ByType:         make(map[string]int),
	}

	for _, e := range processedEvents {
		stats.ByPriority[e.Priority]++
		for _, tag := range e.Tags {
			stats.ByType[tag]++
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}

func processedHandler(w http.ResponseWriter, r *http.Request) {
	mu.Lock()
	defer mu.Unlock()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(processedEvents)
}

func main() {
	port := os.Getenv("PROCESSOR_PORT")
	if port == "" {
		port = "8081"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/process", processHandler)
	mux.HandleFunc("/stats", statsHandler)
	mux.HandleFunc("/processed", processedHandler)

	srv := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	go func() {
		logger.Printf("Starting processor on port %s", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Fatalf("Server failed: %v", err)
		}
	}()

	<-ctx.Done()
	stop()
	logger.Println("Shutting down gracefully...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Fatalf("Forced shutdown: %v", err)
	}
	logger.Println("Server stopped")
}
