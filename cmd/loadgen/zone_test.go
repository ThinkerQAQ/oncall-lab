package main

import (
	"testing"
	"time"
)

func TestParseZoneRoutes(t *testing.T) {
	routes, err := parseZoneRoutes("zone-a|http://gateway-zone-a1:8080/metadata|3,zone-b|http://gateway-zone-b1:8080/metadata|1")
	if err != nil || len(routes) != 4 {
		t.Fatalf("want four weighted routes, got %d, err=%v", len(routes), err)
	}
	if routes[0].zone != "zone-a" || routes[3].zone != "zone-b" {
		t.Fatalf("unexpected routes %#v", routes)
	}
}

func TestRoutesRejectExternalAndMalformedTargets(t *testing.T) {
	for _, raw := range []string{
		"zone-a|https://example.com/metadata|1",
		"zone-a|http://example.com/metadata|1",
		"zone-a|http://127.0.0.2:8080/metadata|1",
		"zone-a|http://gateway-zone-a1:8080/metadata|0",
		"zone-z|http://gateway-zone-z1:8080/metadata|1",
		"zone-a|http://gateway-zone-a1:8080/private|1",
	} {
		if _, err := parseZoneRoutes(raw); err == nil {
			t.Fatalf("expected error for %q", raw)
		}
	}
}

func TestScenarioPhases(t *testing.T) {
	for _, tt := range []struct {
		elapsed time.Duration
		want    string
	}{
		{0, "baseline"},
		{9 * time.Second, "baseline"},
		{10 * time.Second, "incident"},
		{29 * time.Second, "incident"},
		{30 * time.Second, "recovery"},
	} {
		if got := phaseForElapsed(tt.elapsed, 10*time.Second, 20*time.Second); got != tt.want {
			t.Errorf("elapsed %s: got %s, want %s", tt.elapsed, got, tt.want)
		}
	}
}

func TestZoneFailureInjection(t *testing.T) {
	if !shouldInjectZoneDelay("incident", "zone-a", 19, 20) {
		t.Fatal("expected a synthetic zone-a failure within 20%")
	}
	for _, tt := range []struct {
		phase, zone   string
		sequence, pct int
	}{
		{"incident", "zone-a", 25, 20},
		{"baseline", "zone-a", 19, 20},
		{"recovery", "zone-a", 19, 20},
		{"incident", "zone-b", 19, 20},
	} {
		if shouldInjectZoneDelay(tt.phase, tt.zone, tt.sequence, tt.pct) {
			t.Fatalf("should not inject on %v", tt)
		}
	}
}
