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
- cmd/loadgen/: bounded synthetic traffic generator. The zoned scenario targets actual Gateway containers and never external hosts.
- compose.zones.yaml: optional three-logical-zone topology, with two real Gateway containers and one Metadata container per zone. All zones remain on one Docker Desktop host; do not present them as real physical availability zones.
- observability/prometheus/prometheus-zones.yml: actual container scrape targets with logical zone labels.
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

### Independent logical-zone experiment

Base images are built once and reused by the real Gateway/Metadata containers in all three zones. This is a **synthetic application-level fault-injection demonstration on one physical Docker host**, not a three-datacenter or network-partition test. Every Gateway DNS target corresponds to one real Compose container. Only a controlled 20% subset of the `zone-a` requests receive an injected delay during the incident phase; Kitex itself enforces the timeout.

~~~sh
docker compose -f compose.yaml -f compose.zones.yaml up -d --build
docker compose -f compose.yaml -f compose.zones.yaml run --rm -e BASELINE_SECONDS=10 -e INCIDENT_SECONDS=20 -e RECOVERY_SECONDS=10 loadgen-zones
~~~

The default run has longer phases (25s / 50s / 25s). Query the Prometheus `kitex-gateway` job using `zone` and `instance` labels or open the `oncall-zones` Grafana dashboard. Framework-generated RPC counters use the `kitex_client_throughput` and `kitex_server_throughput` names, and can be compared to the application-observed timeout counters. Do not interpret server-success and client-timeout differences as proof of a specific network root cause.

This scenario is not a substitute for Kubernetes rolling-updates or discovery-convergence experiments. Those require separate Kind/Kubernetes topology and explicit test evidence.

## Reproducible experiment scenarios

All commands below are scoped to Oncall Lab; neither Kind nor Docker networks are physical availability zones.

- Three-phase logical-zone RPC timeout: docker compose -f compose.yaml -f compose.zones.yaml run --rm --no-deps loadgen-zones (traffic profile and environment from compose.zones.yaml).
- Real Kitex transport outage with cleanup: scripts/scenarios/connection-unavailable.sh.
- Actual container-start/image-ID change timeline: scripts/scenarios/record-change.sh; this is a *same-image recreation*, not a code release.
- Isolated Kubernetes lifecycle: k8s/up.sh (also restores a safe localhost:28084 port-forward), then k8s/drain.sh and k8s/lifecycle.sh.
- Real rolling restart under concurrent Kitex RPC traffic: python3 k8s/rollout-traffic.py; preserve actual per-request status/latency evidence and do not assume it will be error-free.
- Kind-only HPA: k8s/metrics-server.sh then k8s/hpa.sh; CPU load and HPA must be cleaned up even if a test fails.
- Real connection reuse / uneven service-endpoint traffic: k8s/port-forward.sh exposes only localhost:28084 and automatically restores the scoped forward after a Gateway rollout; then python3 k8s/load-balancing.py measures real per-Pod counters before/after.
- Snapshots and real Grafana screenshots belong in ignored evidence/; never fabricate missing data.

Metrics values are comparable only within the same measurement window and scrape-target lifetime. A single-host Kind simulation cannot verify real multi-region isolation, physical network conditions, proprietary mesh error codes, or production Consul convergence.

## Git workflow

- Initial bootstrap may create the first commit on an empty repository; subsequent changes go through feature branches and pull requests.
- Inspect Git status and the diff before committing.
- Use squash merge after review and delete stale feature branches.
- Keep README.md and README_ZH.md aligned. They are intentionally brief at this stage.
- Never touch other repositories' README without explicit user approval.
