package main

import (
	"context"
	"errors"
	"testing"

	"github.com/ThinkerQAQ/oncall-lab/kitex_gen/metadata"
	"github.com/cloudwego/kitex/pkg/kerrors"
	"github.com/prometheus/client_golang/prometheus"
)

func testHandler() *handler {
	return &handler{
		requests: prometheus.NewCounterVec(prometheus.CounterOpts{Name: "test_rpc_server_requests_total"}, []string{"result"}),
		duration: prometheus.NewHistogramVec(prometheus.HistogramOpts{Name: "test_rpc_server_duration_seconds"}, []string{}),
	}
}

func TestGetMetadata(t *testing.T) {
	h := testHandler()
	response, err := h.GetMetadata(context.Background(), &metadata.GetMetadataRequest{ArticleId: "demo"})
	if err != nil || response.ArticleId != "demo" || response.Title == "" {
		t.Fatalf("unexpected response: %#v, err=%v", response, err)
	}
}

func TestGetMetadataRejectsInvalidInput(t *testing.T) {
	h := testHandler()
	if _, err := h.GetMetadata(context.Background(), &metadata.GetMetadataRequest{}); err == nil {
		t.Fatal("missing article ID must be rejected")
	}
	bad := int32(4000)
	if _, err := h.GetMetadata(context.Background(), &metadata.GetMetadataRequest{ArticleId: "demo", DelayMs: &bad}); err == nil {
		t.Fatal("delay > 3000ms must be rejected")
	}
}

func TestGetMetadataHonorsCancellation(t *testing.T) {
	h := testHandler()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	slow := int32(1500)
	_, err := h.GetMetadata(ctx, &metadata.GetMetadataRequest{ArticleId: "demo", DelayMs: &slow})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected cancellation, got %v", err)
	}
}

func TestGetMetadataSyntheticApplicationError(t *testing.T) {
	h := testHandler()
	_, err := h.GetMetadata(context.Background(), &metadata.GetMetadataRequest{ArticleId: "synthetic-application-error"})
	bizErr, ok := kerrors.FromBizStatusError(err)
	if !ok || bizErr.BizStatusCode() != 2101 {
		t.Fatalf("expected Kitex synthetic biz error code 2101, got %v", err)
	}
}
