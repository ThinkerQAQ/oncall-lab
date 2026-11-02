package main

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata"
	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata/metadataservice"
	"github.com/cloudwego/kitex/server"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type handler struct {
	requests *prometheus.CounterVec
	duration *prometheus.HistogramVec
}

func (h *handler) GetMetadata(ctx context.Context, req *metadata.GetMetadataRequest) (*metadata.GetMetadataResponse, error) {
	begin := time.Now()
	defer func() { h.duration.WithLabelValues().Observe(time.Since(begin).Seconds()) }()

	if req == nil || req.GetArticleId() == "" {
		h.requests.WithLabelValues("invalid_request").Inc()
		return nil, errors.New("article_id is required")
	}
	// Only the synthetic lab workload may request an artificial delay.
	delayMs := req.GetDelayMs()
	if delayMs < 0 || delayMs > 3000 {
		h.requests.WithLabelValues("invalid_delay").Inc()
		return nil, errors.New("delay_ms must be in [0, 3000]")
	}
	if delayMs > 0 {
		select {
		case <-time.After(time.Duration(delayMs) * time.Millisecond):
		case <-ctx.Done():
			h.requests.WithLabelValues("cancelled").Inc()
			return nil, ctx.Err()
		}
	}
	h.requests.WithLabelValues("success").Inc()
	return &metadata.GetMetadataResponse{ArticleId: req.GetArticleId(), Title: "Synthetic article " + req.GetArticleId()}, nil
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	address := getEnv("RPC_LISTEN", ":8888")
	metricsAddr := getEnv("METRICS_LISTEN", ":9091")
	addr, err := net.ResolveTCPAddr("tcp", address)
	if err != nil {
		log.Error("invalid RPC_LISTEN", "error", err)
		os.Exit(1)
	}
	requests := prometheus.NewCounterVec(prometheus.CounterOpts{Name: "rpc_server_requests_total", Help: "Synthetic Kitex RPC server request outcomes."}, []string{"result"})
	duration := prometheus.NewHistogramVec(prometheus.HistogramOpts{Name: "rpc_server_duration_seconds", Help: "Synthetic Kitex RPC server handler duration."}, []string{})
	registry := prometheus.NewRegistry()
	registry.MustRegister(requests, duration)
	metrics := http.NewServeMux()
	metrics.Handle("/metrics", promhttp.HandlerFor(registry, promhttp.HandlerOpts{}))
	metrics.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	go func() {
		if err := http.ListenAndServe(metricsAddr, metrics); err != nil {
			log.Error("metrics server terminated", "error", err)
		}
	}()
	srv := metadataservice.NewServer(&handler{requests: requests, duration: duration}, server.WithServiceAddr(addr))
	log.Info("Kitex metadata service listening", "rpc", address, "metrics", metricsAddr, "example_delay_ms", strconv.Itoa(1500))
	if err := srv.Run(); err != nil {
		log.Error("Kitex server terminated", "error", err)
		os.Exit(1)
	}
}

func getEnv(k, defaultValue string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return defaultValue
}
