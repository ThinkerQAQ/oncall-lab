package main

import (
	"context"
	"errors"
	"github.com/ThinkerQAQ/oncall-lab/internal/lablog"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata"
	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata/metadataservice"
	"github.com/cloudwego/kitex/pkg/rpcinfo"
	"github.com/cloudwego/kitex/server"
	kitexprom "github.com/kitex-contrib/monitor-prometheus"
	"github.com/kitex-contrib/obs-opentelemetry/provider"
	oteltracing "github.com/kitex-contrib/obs-opentelemetry/tracing"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

type handler struct {
	requests *prometheus.CounterVec
	duration *prometheus.HistogramVec
	log      *slog.Logger
}

func (h *handler) GetMetadata(ctx context.Context, req *metadata.GetMetadataRequest) (*metadata.GetMetadataResponse, error) {
	begin := time.Now()
	defer func() { h.duration.WithLabelValues().Observe(time.Since(begin).Seconds()) }()

	if req == nil || req.GetArticleId() == "" {
		h.requests.WithLabelValues("invalid_request").Inc()
		return nil, errors.New("article_id is required")
	}
	// A deliberately synthetic application handler failure is distinct from a
	// framework deadline or network failure. No private error codes are used.
	if req.GetArticleId() == "synthetic-application-error" {
		h.requests.WithLabelValues("application_error").Inc()
		h.logResult(ctx, "application_error", 0, time.Since(begin))
		return nil, errors.New("synthetic injected application handler error")
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
			h.logResult(ctx, "cancelled", delayMs, time.Since(begin))
			return nil, ctx.Err()
		}
	}
	h.requests.WithLabelValues("success").Inc()
	h.logResult(ctx, "success", delayMs, time.Since(begin))
	return &metadata.GetMetadataResponse{ArticleId: req.GetArticleId(), Title: "Synthetic article " + req.GetArticleId()}, nil
}

func (h *handler) logResult(ctx context.Context, result string, delayMs int32, elapsed time.Duration) {
	if h.log == nil {
		return
	}
	span := trace.SpanFromContext(ctx)
	h.log.Info("synthetic Kitex server handled RPC", "result", result, "delay_ms", delayMs, "duration_ms", elapsed.Milliseconds(), "trace_id", span.SpanContext().TraceID().String(), "zone", getEnv("LAB_ZONE", "standalone"), "instance", getEnv("LAB_INSTANCE", "metadata"))
}

func main() {
	log, closeLog := lablog.New("metadata")
	defer closeLog()
	telemetry := provider.NewOpenTelemetryProvider(
		provider.WithServiceName("MetadataService"),
		provider.WithDeploymentEnvironment("lab"),
		provider.WithResourceAttribute(attribute.String("service.instance.id", getEnv("LAB_INSTANCE", "metadata"))),
		provider.WithResourceAttribute(attribute.String("lab.zone", getEnv("LAB_ZONE", "standalone"))),
		provider.WithExportEndpoint(getEnv("OTEL_EXPORTER_ENDPOINT", "tempo:4317")),
		provider.WithInsecure(),
		provider.WithEnableMetrics(false),
	)
	if telemetry == nil {
		log.Error("OpenTelemetry trace provider is disabled")
		os.Exit(1)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := telemetry.Shutdown(shutdownCtx); err != nil {
			log.Error("OpenTelemetry shutdown failed", "error", err)
		}
	}()

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
	srv := metadataservice.NewServer(
		&handler{requests: requests, duration: duration, log: log},
		server.WithServiceAddr(addr),
		server.WithServerBasicInfo(&rpcinfo.EndpointBasicInfo{ServiceName: "MetadataService"}),
		server.WithSuite(oteltracing.NewServerSuite()),
		server.WithTracer(kitexprom.NewServerTracer("", "", kitexprom.WithRegistry(registry), kitexprom.WithDisableServer(true))),
	)
	log.Info("Kitex metadata service listening", "rpc", address, "metrics", metricsAddr, "example_delay_ms", strconv.Itoa(1500), "zone", getEnv("LAB_ZONE", "standalone"))
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
