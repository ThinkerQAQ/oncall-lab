# Oncall Lab

A private, reproducible engineering lab for investigating production-style failures using **Go, Kitex (Thrift RPC), Docker Compose, and open-source observability**.

The lab is independent of any employer's internal systems. Its workloads, topology, errors, and data are synthetic.

## Scope

- **RPC:** Gateway → Kitex Metadata Service; a real Thrift call with a configurable client timeout.
- **Observability:** Prometheus, Grafana, Loki, and Tempo in one Docker Compose project.
- **Experiments:** RPC timeouts first; load balancing, discovery, graceful shutdown, and rollout behavior in later stages.

The initial repository is an environment bootstrap, not a reproduction of an actual production incident. Metrics from the gateway and metadata service are wired; Loki log shipping and Tempo tracing are provisioned but will be connected in the scenario implementation.

## Run

~~~sh
cp .env.example .env   # Set your own Grafana admin password in .env
docker compose up -d --build
curl 'http://127.0.0.1:28080/metadata?id=demo'
~~~

Grafana: http://127.0.0.1:23000

To stop:

~~~sh
docker compose down
~~~

Services and development commands are kept in AGENTS.md. No proprietary code, internal configurations, or production screenshots belong in this repository.
