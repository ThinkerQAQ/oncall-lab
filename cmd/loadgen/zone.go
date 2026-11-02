package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"
)

type zoneRoute struct {
	zone     string
	endpoint string
}

type zoneStat struct {
	sent   int
	failed int
}

// parseZoneRoutes limits the generator to loopback or Docker service names.
// It cannot send this synthetic experiment's traffic to public hosts.
func parseZoneRoutes(raw string) ([]zoneRoute, error) {
	var routes []zoneRoute
	for _, entry := range strings.Split(raw, ",") {
		fields := strings.Split(strings.TrimSpace(entry), "|")
		if len(fields) != 3 {
			return nil, errors.New("routes must be zone|http://docker-service:port/metadata|weight")
		}
		zone := fields[0]
		if zone != "zone-a" && zone != "zone-b" && zone != "zone-c" {
			return nil, errors.New("route zone must be zone-a, zone-b or zone-c")
		}
		u, err := url.Parse(fields[1])
		if err != nil || u.Scheme != "http" || u.User != nil || u.Host == "" || u.Path != "/metadata" || u.RawQuery != "" || u.Fragment != "" {
			return nil, errors.New("route must be a plain HTTP /metadata endpoint")
		}
		host := u.Hostname()
		if host != "localhost" && host != "127.0.0.1" && (strings.Contains(host, ".") || net.ParseIP(host) != nil) {
			return nil, errors.New("route must use a Docker service name or local loopback")
		}
		weight, err := strconv.Atoi(fields[2])
		if err != nil || weight < 1 || weight > 10 {
			return nil, errors.New("route weight must be 1..10")
		}
		for i := 0; i < weight; i++ {
			routes = append(routes, zoneRoute{zone: zone, endpoint: fields[1]})
		}
		if len(routes) > 60 {
			return nil, errors.New("sum of route weights must not exceed 60")
		}
	}
	if len(routes) == 0 {
		return nil, errors.New("no routes configured")
	}
	return routes, nil
}

func phaseForElapsed(elapsed, baseline, incident time.Duration) string {
	switch {
	case elapsed < baseline:
		return "baseline"
	case elapsed < baseline+incident:
		return "incident"
	default:
		return "recovery"
	}
}

func shouldInjectZoneDelay(phase, zone string, sequence, percentage int) bool {
	return phase == "incident" && zone == "zone-a" && (sequence%100) < percentage
}

func runZoneScenario() {
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	routes, err := parseZoneRoutes(os.Getenv("ZONE_ROUTES"))
	if err != nil {
		log.Error("invalid zone routes", "error", err)
		os.Exit(2)
	}
	qps := envInt("QPS", 22)
	baseline := envInt("BASELINE_SECONDS", 25)
	incident := envInt("INCIDENT_SECONDS", 50)
	recovery := envInt("RECOVERY_SECONDS", 25)
	failPercent := envInt("ZONE_A_FAIL_PERCENT", 20)
	if qps < 1 || qps > 60 || baseline < 5 || incident < 5 || recovery < 5 || baseline+incident+recovery > 300 || failPercent < 0 || failPercent > 100 {
		log.Error("invalid load bounds")
		os.Exit(2)
	}
	total := time.Duration(baseline+incident+recovery) * time.Second
	client := &http.Client{Timeout: 3 * time.Second}
	ticker := time.NewTicker(time.Second / time.Duration(qps))
	defer ticker.Stop()
	start := time.Now()
	deadline := start.Add(total)
	var wg sync.WaitGroup
	sem := make(chan struct{}, 64)
	stats := make(map[string]*zoneStat)
	var mu sync.Mutex
	count := 0
	currentPhase := ""
	log.Info("synthetic zone experiment started", "qps", qps, "duration_seconds", int(total.Seconds()), "routes", len(routes), "zone_a_fail_percent", failPercent)
	for time.Now().Before(deadline) {
		<-ticker.C
		phase := phaseForElapsed(time.Since(start), time.Duration(baseline)*time.Second, time.Duration(incident)*time.Second)
		if phase != currentPhase {
			currentPhase = phase
			log.Info("experiment phase", "phase", phase)
		}
		r := routes[count%len(routes)]
		count++
		sem <- struct{}{}
		wg.Add(1)
		go func(route zoneRoute, phase string, sequence int) {
			defer wg.Done()
			defer func() { <-sem }()
			u, _ := url.Parse(route.endpoint)
			q := u.Query()
			q.Set("id", fmt.Sprintf("synthetic-%d", sequence))
			if shouldInjectZoneDelay(phase, route.zone, sequence, failPercent) {
				// Deliberately make RPC handler slower than Kitex's timeout.
				// This is application-level fault injection, NOT real AZ networking.
				q.Set("delay_ms", "1500")
			}
			u.RawQuery = q.Encode()
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
			failed := err != nil
			if !failed {
				resp, reqErr := client.Do(req)
				failed = reqErr != nil
				if reqErr == nil {
					_, _ = io.Copy(io.Discard, resp.Body)
					_ = resp.Body.Close()
					failed = resp.StatusCode != http.StatusOK
				}
			}
			mu.Lock()
			key := phase + "/" + route.zone + "/" + route.endpoint
			stat := stats[key]
			if stat == nil {
				stat = &zoneStat{}
				stats[key] = stat
			}
			stat.sent++
			if failed {
				stat.failed++
			}
			mu.Unlock()
		}(r, phase, count)
	}
	wg.Wait()
	for key, count := range stats {
		log.Info("experiment observed requests", "phase_zone_target", key, "sent", count.sent, "failed", count.failed)
	}
	log.Info("synthetic zone experiment finished", "total_requests", count)
}
