#!/usr/bin/env bash
# Actual CPU-based Kubernetes HPA scaling, not kubectl scale.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
ns=oncall-lab
cleanup() {
  echo '[CLEANUP] Stop synthetic CPU workload, remove HPA, restore six replicas'
  for pod in $("$k" -n "$ns" get pods -l app=metadata -o jsonpath='{.items[*].metadata.name}' 2>/dev/null);do
    "$k" -n "$ns" exec "$pod" -- sh -c 'if test -f /tmp/oncall-cpu-load.pid; then kill $(cat /tmp/oncall-cpu-load.pid) 2>/dev/null || true; rm -f /tmp/oncall-cpu-load.pid; fi' >/dev/null 2>&1 || true
  done
  "$k" -n "$ns" delete hpa metadata-cpu --ignore-not-found >/dev/null || true
  "$k" -n "$ns" scale deployment/metadata --replicas=6 >/dev/null || true
  "$k" -n "$ns" rollout status deployment/metadata --timeout=120s >/dev/null || true
  k8s/rebalance.sh || true
}
trap cleanup EXIT INT TERM
k8s/check.sh
"$k" -n "$ns" apply -f k8s/hpa.yaml
for pod in $("$k" -n "$ns" get pods -l app=metadata -o jsonpath='{.items[*].metadata.name}'); do
  "$k" -n "$ns" exec "$pod" -- sh -c 'nohup yes >/dev/null 2>&1 & echo $! >/tmp/oncall-cpu-load.pid'
  echo "Injected lab CPU workload in $pod"
done
seen=0
for i in $(seq 1 45); do
  desired="$($k -n "$ns" get deployment metadata -o jsonpath='{.spec.replicas}')"
  echo "check $i: desired_replica_count=$desired"
  if [ "$desired" -gt 6 ];then
    seen=1
    "$k" -n "$ns" get hpa metadata-cpu
    "$k" -n "$ns" get deployment metadata
    "$k" -n "$ns" get hpa metadata-cpu -o json > evidence/kind-hpa-scaleup.json
    break
  fi
  sleep 3
done
if [ "$seen" -ne 1 ]; then
  echo 'No HPA scale-up observed; inspect metrics-server and CPU requests' >&2
  "$k" -n "$ns" describe hpa metadata-cpu | tail -40
  exit 5
fi
printf 'PASS: Kubernetes HPA increased desired Metadata replicas above 6 due to actual CPU usage\n'
