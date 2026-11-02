#!/usr/bin/env bash
# Preserve one real Pod while removing it from Ready Service endpoints.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
ns=oncall-lab
pod="$($k -n "$ns" get pods -l app=metadata -o json | python3 -c 'import json,sys;x=json.load(sys.stdin)["items"];print(next(p["metadata"]["name"] for p in x if p["spec"]["nodeName"]=="oncall-lab-kind-worker"))')"
echo "Target real zone-A Pod: $pod"
ready_endpoints() {
  "$k" -n "$ns" get endpointslices -l kubernetes.io/service-name=metadata -o json |
    python3 -c 'import json,sys;d=json.load(sys.stdin);print(sum(1 for x in d["items"] for e in x.get("endpoints",[]) if e.get("conditions",{}).get("ready")))'
}
test "$(ready_endpoints)" = 6
recover() {
  "$k" -n "$ns" exec "$pod" -- rm -f /tmp/oncall-not-ready >/dev/null || true
}
trap recover EXIT INT TERM
"$k" -n "$ns" exec "$pod" -- touch /tmp/oncall-not-ready
for i in $(seq 1 30); do
  ready=$($k -n "$ns" get pod "$pod" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
  if [ "$ready" = False ]; then break; fi
  sleep 2
done
if [ "$ready" != False ]; then echo 'Pod did not become NotReady' >&2;exit 3;fi
# Pod is running but deliberately no longer a healthy Service endpoint.
phase=$($k -n "$ns" get pod "$pod" -o jsonpath='{.status.phase}')
test "$phase" = Running
"$k" -n "$ns" exec "$pod" -- wget -q -O /dev/null http://127.0.0.1:9091/healthz
# EndpointSlice updates are asynchronous; confirm Kubernetes actually removed traffic.
endpoints="$(ready_endpoints)"
for i in $(seq 1 25); do
  if [ "$endpoints" = 5 ]; then break; fi
  sleep 2
  endpoints="$(ready_endpoints)"
done
test "$endpoints" = 5 || { echo "Expected 5 ready endpoints, got $endpoints" >&2; exit 4; }
printf 'PASS: Pod stays Running; liveness 200; ready EndpointSlice count drops 6 -> 5\n'
recover
trap - EXIT INT TERM
for i in $(seq 1 30);do
 ready=$($k -n "$ns" get pod "$pod" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
 if [ "$ready" = True ];then break;fi
 sleep 2
done
test "$ready" = True
for i in $(seq 1 25); do
  if [ "$(ready_endpoints)" = 6 ]; then break; fi
  sleep 2
done
k8s/check.sh
printf 'PASS: traffic readiness restored without deleting the Pod\n'
