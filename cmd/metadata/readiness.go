package main

import "os"

// readyForTraffic models a readiness signal independently of liveness.
// Only enabled when LAB_UNREADY_FILE is set, for Kind lifecycle experiments.
func readyForTraffic(marker string) bool {
	if marker == "" {
		return true
	}
	_, err := os.Stat(marker)
	return os.IsNotExist(err)
}
