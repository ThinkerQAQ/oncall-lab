# Oncall Lab — Agent Rules

## Goal and boundaries

Build a reproducible, independent fault-investigation lab for a public engineering article. Use Go and open-source Kitex/Thrift RPC. The repository is private during development.

- **Never import** internal company source code, service names, confidential topology, runbooks, credentials, production logs, screenshots, or values.
- Label all traffic, metrics, traces, and screenshots as **synthetic experiment evidence**. Do not present fault-injection causes as historical production root causes.
- Do not invent screenshots, metric measurements, trace spans, deployment events, or benchmark results.
- Do not confuse the standalone observability lab with an actual multi-region, Kubernetes, or service-mesh deployment.
- Keep this project independent from the performance-analysis example.

## Source map

- idl/metadata.thrift: Thrift contract.
- kitex_gen/: generated Go client/server code; regenerate from the IDL, do not hand-edit.
- cmd/metadata/: actual Kitex RPC server.
- cmd/gateway/: HTTP entrypoint that makes real Kitex RPC calls.
- cmd/loadgen/: reserved for controlled synthetic traffic.
- observability/: Grafana/Prometheus/Loki/Tempo configuration.
- Dockerfile: shared multistage image build, selected with TARGET.
- compose.yaml: single entrypoint for reproducible local environments.

## Engineering rules

1. Prefer the upstream Kitex and OpenTelemetry SDKs over manually fabricated protocol or trace data.
2. Every new incident scenario must have a baseline, a fault-injection phase, a recovery phase, and an explicit validation query. Restore the environment after testing.
3. Measure request rates and **failure ratios** with consistent collection points, time ranges and label grouping.
4. Distinguish client-observed RPC timeout from downstream processing time. Client spans alone cannot prove a network fault.
5. Do not silently create fictitious zones or instances and call them physical data centers or real containers.
6. Keep runtime data and secrets out of git. Docker services should expose only necessary loopback ports.
7. No production-external requests, privileged network probes, or unauthorized traffic capture.
8. Do not commit generated screenshots until the experiment that produced them is documented.
9. Do not modify any other repository's README, article, or assets without explicit approval.
10. Do not make the private repository public, publish release artifacts, or merge branches without approval.

## Verification

Before a commit or PR:

~~~sh
go test ./...
go vet ./...
docker compose config --quiet
docker compose up -d --build
curl -fsS 'http://127.0.0.1:28080/metadata?id=demo'
docker compose ps
~~~

If Docker Desktop is not shared with WSL, report the blocker instead of claiming the containers were tested. Go tests are not equivalent to a successful Docker build.

## Git workflow

- Initial bootstrap may create the first commit on an empty repository; subsequent changes go through feature branches and pull requests.
- Inspect Git status and the diff before committing.
- Use squash merge after review and delete stale feature branches.
- Keep README.md and README_ZH.md aligned. They are intentionally brief at this stage.
- Never touch other repositories' README without explicit user approval.
