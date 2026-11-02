package main

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata"
	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata/metadataservice"
	"github.com/cloudwego/kitex/client"
	"github.com/cloudwego/kitex/pkg/kerrors"
	"github.com/cloudwego/kitex/pkg/rpcinfo"
	kitexprom "github.com/kitex-contrib/monitor-prometheus"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type gateway struct {
	rpc      metadataservice.Client
	requests *prometheus.CounterVec
	duration prometheus.Observer
	log      *slog.Logger
}

func (g *gateway) handleMetadata(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	id := r.URL.Query().Get("id")
	if id == "" {
		http.Error(w, "id is required", http.StatusBadRequest)
		return
	}
	var delay *int32
	if raw := r.URL.Query().Get("delay_ms"); raw != "" {
		n, err := strconv.ParseInt(raw, 10, 32)
		if err != nil || n < 0 || n > 3000 {
			http.Error(w, "delay_ms must be between 0 and 3000", http.StatusBadRequest)
			return
		}
		v := int32(n)
		delay = &v
	}
	begin := time.Now()
	resp, err := g.rpc.GetMetadata(r.Context(), &metadata.GetMetadataRequest{ArticleId: id, DelayMs: delay})
	dur := time.Since(begin)
	result := "success"
	status := http.StatusOK
	if err != nil {
		result = "rpc_error"
		status = http.StatusBadGateway
		if kerrors.IsTimeoutError(err) || errors.Is(err, context.DeadlineExceeded) {
			result = "timeout"
			status = http.StatusGatewayTimeout
		}
		g.log.Error("synthetic Kitex RPC failed", "result", result, "duration_ms", dur.Milliseconds(), "error", err.Error())
	} else {
		g.log.Info("synthetic Kitex RPC completed", "result", result, "duration_ms", dur.Milliseconds())
	}
	g.requests.WithLabelValues(result).Inc()
	g.duration.Observe(dur.Seconds())
	w.Header().Set("X-Lab-Zone", getEnv("LAB_ZONE", "standalone"))
	w.Header().Set("X-Lab-Instance", getEnv("LAB_INSTANCE", "gateway"))
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err != nil {
		_ = json.NewEncoder(w).Encode(map[string]any{"result": result, "duration_ms": dur.Milliseconds()})
		return
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"article_id": resp.ArticleId, "title": resp.Title, "duration_ms": dur.Milliseconds()})
}

func main() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	addr := getEnv("HTTP_LISTEN", ":8080")
	rpcAddress := getEnv("METADATA_RPC_ADDR", "metadata:8888")
	registry := prometheus.NewRegistry()
	rpc, err := metadataservice.NewClient("MetadataService",
		client.WithHostPorts(rpcAddress),
		client.WithClientBasicInfo(&rpcinfo.EndpointBasicInfo{ServiceName: "GatewayService"}),
		client.WithRPCTimeout(1200*time.Millisecond),
		client.WithConnectTimeout(200*time.Millisecond),
		client.WithTracer(kitexprom.NewClientTracer("", "", kitexprom.WithRegistry(registry), kitexprom.WithDisableServer(true))))
	if err != nil {
		log.Error("create Kitex client", "error", err)
		os.Exit(1)
	}
	reqs := prometheus.NewCounterVec(prometheus.CounterOpts{Name: "rpc_client_requests_total", Help: "Synthetic Kitex RPC client outcomes."}, []string{"result"})
	dur := prometheus.NewHistogram(prometheus.HistogramOpts{Name: "rpc_client_duration_seconds", Help: "Kitex GetMetadata RPC duration observed at the gateway."})
	registry.MustRegister(reqs, dur)
	g := &gateway{rpc: rpc, requests: reqs, duration: dur, log: log}
	mux := http.NewServeMux()
	mux.HandleFunc("/metadata", g.handleMetadata)
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
	mux.Handle("/metrics", promhttp.HandlerFor(registry, promhttp.HandlerOpts{}))
	srv := &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdownCtx)
	}()
	log.Info("Gateway listening", "address", addr, "rpc_target", rpcAddress, "zone", getEnv("LAB_ZONE", "standalone"), "instance", getEnv("LAB_INSTANCE", "gateway"))
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Error("gateway terminated", "error", err)
		os.Exit(1)
	}
}

func getEnv(k, defaultValue string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return defaultValue
}
