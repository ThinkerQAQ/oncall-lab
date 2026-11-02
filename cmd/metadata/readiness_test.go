package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadinessMarker(t *testing.T) {
	marker := filepath.Join(t.TempDir(), "not-ready")
	if !readyForTraffic("") || !readyForTraffic(marker) {
		t.Fatal("ready before marker exists")
	}
	if err := os.WriteFile(marker, []byte("unready"), 0600); err != nil {
		t.Fatal(err)
	}
	if readyForTraffic(marker) {
		t.Fatal("file marker should make readiness fail")
	}
	if err := os.Remove(marker); err != nil {
		t.Fatal(err)
	}
	if !readyForTraffic(marker) {
		t.Fatal("must recover after removing marker")
	}
}
