// Package lablog writes synthetic experiment events to stdout and an optional
// shared Docker volume, where Promtail can safely scrape files without access
// to the Docker daemon or its privileged socket.
package lablog

import (
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"regexp"
)

var safeName = regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`)

// New returns a JSON logger and a shutdown hook; it never prevents service
// startup if a logging volume is not present (e.g. in unit tests).
func New(defaultInstance string) (*slog.Logger, func()) {
	name := os.Getenv("LAB_INSTANCE")
	if name == "" {
		name = defaultInstance
	}
	if !safeName.MatchString(name) {
		name = defaultInstance
	}
	var output io.Writer = os.Stdout
	var closeFn = func() {}
	path := os.Getenv("LAB_LOG_DIR")
	if path != "" {
		file, err := os.OpenFile(filepath.Join(path, name+".jsonl"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
		if err == nil {
			output = io.MultiWriter(os.Stdout, file)
			closeFn = func() { _ = file.Close() }
		} else {
			slog.Error("unable to open lab log file; writing stdout only", "error", err.Error())
		}
	}
	return slog.New(slog.NewJSONHandler(output, nil)), closeFn
}
