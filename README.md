# Oncall Lab

A reproducible fault-investigation lab using **Go, Kitex (Thrift RPC), Docker Compose, Prometheus, Grafana, Loki, Tempo, Mailpit, and Kubernetes (Kind)**. Start from an actual delivered alert, then investigate metrics, logs, traces, and running code.

All services, traffic, errors, and fault domains are **synthetic**. Neither the Docker logical zones nor the Kind worker-zone labels represent physical availability zones.

## Contents

1. [Introduction](#1-introduction)
2. [Architecture](#2-architecture)
3. [Quick Start](#3-quick-start)
4. [Experiment Scenarios](#4-experiment-scenarios)
5. [Configuration Reference](#5-configuration-reference)
6. [Troubleshooting](#6-troubleshooting)
7. [Development and Cleanup](#7-development-and-cleanup)

## 1. Introduction

The main case is a **real Kitex RPC timeout caused by controlled server-side delay**. Six Gateway processes call six Metadata processes across three logical zones. During the incident, a subset of Zone A requests takes 1,500 ms to process, exceeding the client's 1,200 ms RPC deadline.

Kitex and Prometheus report actual RPC metrics; Promtail/Loki collect JSON logs; OpenTelemetry/Tempo record correlated client/server spans. Grafana evaluates **P2 / Warning** (timeout QPS) and **P1 / Critical** (Zone A timeout ratio above 25% for 20 seconds) and sends real SMTP notifications to a **local Mailpit inbox**, with no external recipient.

Separate Kind experiments cover Kubernetes rollout, autoscaling, traffic draining, endpoint distribution, and Pod replacement. A client timeout does not necessarily mean its server handler failed.

## 2. Architecture

~~~text
Synthetic load generator
  ├── Zone A: Gateway A1/A2 ── Kitex/Thrift ── Metadata A1/A2
  ├── Zone B: Gateway B1/B2 ── Kitex/Thrift ── Metadata B1/B2
  └── Zone C: Gateway C1/C2 ── Kitex/Thrift ── Metadata C1/C2
                      │
                      ├── Kitex/application metrics ── Prometheus
                      ├── JSON logs ── Promtail ── Loki
                      └── OpenTelemetry ── Tempo
                                            │
                       Grafana Dashboard / Explore / Alerting
                                            │
                                  local SMTP ── Mailpit

Separate Kind: control plane + three labeled worker nodes
  └── Deployment / Service / EndpointSlice / HPA
~~~

Gateway → Metadata routing is deliberately one-to-one in the Compose incident so that failures can be verified against **real processes**. It is not a demonstration of production-grade dynamic service discovery. All three Kind zones run on the same physical Docker host.

## 3. Quick Start

### 3.1 Prerequisites

- **Git, Docker Engine / Docker Desktop with Compose v2, Bash, Python 3, and curl**.
- Running Docker daemon: check `docker info` and `docker compose version`.
- Internet access for public container images and Go modules on the first build.
- Free local ports listed in [Configuration Reference](#5-configuration-reference).

On Windows, use **WSL2 with Docker Desktop integration**. Run the commands below in Bash. **Go is not needed on the host for this main Compose scenario**; Docker builds the binaries.

### 3.2 Download and configure

~~~bash
git clone https://github.com/ThinkerQAQ/oncall-lab.git
cd oncall-lab
cp .env.example .env
~~~

Edit `.env` and replace `GRAFANA_ADMIN_PASSWORD` with your **own local password**. This file is Git-ignored.

### 3.3 Run the complete incident

~~~bash
bash scripts/scenarios/replay-alert-notification.sh
~~~

One command builds Gateway, Metadata, and loadgen; starts all zones and **Prometheus, Grafana, Loki, Promtail, Tempo, and Mailpit**; runs **baseline → timeout injection → recovery**; and verifies real request results plus the **P1 and P2 FIRING/RESOLVED emails from this run**.

The script writes local logs and evidence to `evidence/`. Grafana evaluates and groups notifications asynchronously, so email delivery can follow the metric transition.

### 3.4 Verify

| Local entry | Expected outcome |
| --- | --- |
| [Mailpit](http://127.0.0.1:28025) | P1/Critical and P2/Warning, each **FIRING** and **RESOLVED** |
| [Grafana](http://127.0.0.1:23000) | Dashboard, alerts, Prometheus / Loki / Tempo Explore |
| [Prometheus](http://127.0.0.1:23090) | Actual RPC/instance metrics and scrape targets |
| [Zone A Gateway](http://127.0.0.1:28081/metadata?id=demo) | Normal Kitex request returns HTTP 200 |

Log in to Grafana Explore as `demo` using the password in `.env`; anonymous access is Viewer-only. The script checks new Mailpit messages using its start time, rather than mistakenly accepting old email.

Optional manual checks:

~~~bash
python3 scripts/verify_zone_run.py "$(ls -1t evidence/alert-notification-*.log | head -1)"
python3 scripts/verify_mailpit_notifications.py
~~~

The total request count varies with execution timing. Verify **Zone A-only timeouts, recovery, and both notification levels**, rather than requiring the article's exact totals. Mailpit showing a message means it was delivered; **email read is not an incident ACK**.

## 4. Experiment Scenarios

Finish [Quick Start](#3-quick-start) before the standalone Compose cases.

### 4.1 RPC timeout and business error

~~~bash
# Normal Kitex call → HTTP 200
curl 'http://127.0.0.1:28081/metadata?id=demo'

# Handler delay exceeds the 1.2 s client deadline → HTTP 504
curl -i 'http://127.0.0.1:28081/metadata?id=slow&delay_ms=1500'

# Actual Kitex BizStatusError(2101) → HTTP 502
curl -i 'http://127.0.0.1:28081/metadata?id=synthetic-application-error'
~~~

`2101` is a synthetic application error code, not an employer-specific code.

### 4.2 Metrics → Logs → Trace

In Grafana **Explore**, select:

- **Prometheus**: `sum by (zone) (rate(rpc_client_requests_total{result="timeout",zone=~"zone-.*"}[30s]))`
- **Loki**: `{job="oncall-lab",result="timeout"}`. Open a real Gateway error log and copy its `trace_id`.
- **Tempo**: search that Trace ID to inspect Gateway HTTP → Kitex Client → Metadata Server spans.

Compare both sides: a caller may time out at ~1,200 ms while the server completes at ~1,500 ms.

### 4.3 Transport outage with recovery

~~~bash
bash scripts/scenarios/connection-unavailable.sh
~~~

Stops **Zone B1** Metadata, checks actual Kitex transport/connection errors, then restores the instance. A connection failure can still surface as HTTP 504 when retries exhaust the RPC budget.

### 4.4 Change timeline

~~~bash
bash scripts/scenarios/record-change.sh
~~~

Captures actual container start times and image IDs, recreates one Zone C Gateway, then compares snapshots. This verifies **same-image recreation**, not a new-code release. Evidence is stored in `evidence/`.

### 4.5 Kind setup

The Kubernetes scripts are implemented for **Linux amd64, including WSL2**, with Docker. Unlike the main Docker scenario, they also require **Go, curl, and sha256sum** to install Kind and a pinned Linux kubectl. Other architectures have not been verified.

~~~bash
bash k8s/up.sh
bash k8s/check.sh
~~~

Expected: three **logical-zone** worker nodes; six Ready Metadata Pods distributed 2/2/2; six Ready Service endpoints; Gateway forwarded to `127.0.0.1:28084`.

### 4.6 Draining while preserving a Pod

~~~bash
bash k8s/drain.sh
~~~

Expected: a Pod stays Running with healthy liveness, while **Ready endpoints change 6 → 5 → 6**. Existing connections can survive an EndpointSlice update.

### 4.7 Rolling updates, Pod replacement, manual scaling

~~~bash
bash k8s/lifecycle.sh
~~~

Verifies rollout, ReplicaSet replacement of a deleted Pod, and **manual** scale 6 → 9 → 6. This is distinct from HPA.

### 4.8 Automatic CPU scaling (HPA)

~~~bash
bash k8s/metrics-server.sh
bash k8s/hpa.sh
~~~

Installs Metrics Server in this disposable Kind cluster, applies a CPU HPA, and generates bounded CPU load. Verify desired replicas increase above six; the test cleans up HPA/CPU load and restores six replicas. The Metrics Server setup includes a **Kind-only insecure kubelet TLS flag: never use it in production**.

### 4.9 Per-Pod routing and rollout under traffic

~~~bash
python3 k8s/load-balancing.py
python3 k8s/rollout-traffic.py
~~~

The first measures real per-Pod Kitex counters under persistent TCP connection reuse; **equal request distribution is not expected**. The second sends 420 RPCs during a real rollout and records per-request HTTP results to `evidence/`. A successful run does not guarantee zero errors under other workloads.

## 5. Configuration Reference

| Location | Purpose |
| --- | --- |
| `.env` / `GRAFANA_ADMIN_PASSWORD` | Password for local Grafana user `demo`; never commit |
| `compose.yaml` | Base services, observability, loopback ports |
| `compose.zones.yaml` | Three logical zones and real Gateway / Metadata instances |
| `observability/prometheus/` | Kitex/application metrics scrape configuration |
| `observability/grafana/` | Dashboard, P1/P2 rules, local email contact |
| `observability/promtail/`, `loki/`, `tempo/` | Log shipping and distributed tracing |
| `k8s/` | Kind rollout, readiness, autoscaling, recovery |
| `evidence/` / `Data/` | Git-ignored local evidence, kubeconfig, local tools |

Ports on **127.0.0.1**: Grafana `23000`, Mailpit `28025`, Prometheus `23090`, Loki `23100`, Tempo `23200`, standalone Gateway `28080`, zone Gateways `28081`–`28083`, Kind Gateway `28084`. Mailpit SMTP is **not exposed to the host**; nothing is sent to external inboxes.

## 6. Troubleshooting

- **Docker unavailable**: start Docker Desktop / Docker Engine, enable WSL integration if needed, then check `docker info`.
- **Missing Grafana password**: copy `.env.example` to `.env` and set `GRAFANA_ADMIN_PASSWORD`.
- **Port conflict**: check the loopback ports above. The Compose project is named `oncall-lab`.
- **No email yet**: check Mailpit and Grafana; alert grouping and delivery are asynchronous. The complete script verifies **new** messages.
- **No Loki logs**: check `docker compose -f compose.yaml -f compose.zones.yaml ps promtail`. Quick Start explicitly starts the collector.
- **Explore unavailable as anonymous**: sign in to Grafana as `demo`.
- **Kind topology not Ready**: run `bash k8s/check.sh` and `bash k8s/rebalance.sh`; ensure sufficient Docker resources.

## 7. Development and Cleanup

Host-side Go is required for **source development and Kind setup**, not the main Quick Start.

~~~bash
go test ./...
go vet ./...
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 -m unittest discover -s k8s -p 'test_*.py'
docker compose -f compose.yaml -f compose.zones.yaml config --quiet
~~~

Stop the Compose environment **without deleting its Mailpit/log volumes**:

~~~bash
docker compose -f compose.yaml -f compose.zones.yaml down
~~~

Delete the separate Kind cluster only when finished:

~~~bash
"$(go env GOPATH)/bin/kind" delete cluster --name oncall-lab-kind
~~~

`docker compose down -v` **also deletes local named volumes** and is not a normal cleanup command. Do not commit `.env`, `Data/`, or `evidence/`. No internal code, production logs, or real-company incident screenshots belong in this repository.
