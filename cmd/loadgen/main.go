package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"time"
)

func main() {
	if os.Getenv("SCENARIO") == "zone-timeout" {
		runZoneScenario()
		return
	}
	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	gateway := env("GATEWAY_URL", "http://gateway:8080/metadata")
	duration := time.Duration(envInt("DURATION_SECONDS", 45)) * time.Second
	qps := envInt("QPS", 10)
	delay := envInt("DELAY_MS", 0)
	if qps < 1 || qps > 100 || delay < 0 || delay > 3000 {
		log.Error("invalid synthetic load settings", "qps", qps, "delay_ms", delay)
		os.Exit(2)
	}
	client := &http.Client{Timeout: 4 * time.Second}
	ctx, cancel := context.WithTimeout(context.Background(), duration)
	defer cancel()
	ticker := time.NewTicker(time.Second / time.Duration(qps))
	defer ticker.Stop()
	n, bad := 0, 0
	for {
		select {
		case <-ctx.Done():
			log.Info("synthetic load finished", "sent", n, "failed", bad)
			return
		case <-ticker.C:
			u, err := url.Parse(gateway)
			if err != nil {
				log.Error("bad gateway URL", "error", err)
				os.Exit(2)
			}
			q := u.Query()
			q.Set("id", fmt.Sprintf("sample-%d", rand.Intn(1000)))
			q.Set("delay_ms", strconv.Itoa(delay))
			u.RawQuery = q.Encode()
			req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
			if err != nil {
				continue
			}
			res, err := client.Do(req)
			n++
			if err != nil {
				bad++
				continue
			}
			_, _ = io.Copy(io.Discard, res.Body)
			_ = res.Body.Close()
			if res.StatusCode != http.StatusOK {
				bad++
			}
		}
	}
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
func envInt(k string, def int) int {
	n, err := strconv.Atoi(env(k, strconv.Itoa(def)))
	if err != nil {
		return def
	}
	return n
}
