#!/usr/bin/env bash
# Actual Kubernetes rolling update, self-healing and manual scale (not HPA).
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
ns=oncall-lab
k8s/check.sh
before="$($k -n "$ns" get pods -l app=metadata -o jsonpath='{range .items[*]}{.metadata.uid}{" "}{end}')"
"$k" -n "$ns" rollout restart deployment/metadata
"$k" -n "$ns" rollout status deployment/metadata --timeout=180s
k8s/rebalance.sh
k8s/check.sh
after="$($k -n "$ns" get pods -l app=metadata -o jsonpath='{range .items[*]}{.metadata.uid}{" "}{end}')"
if [ "$before" = "$after" ]; then echo 'Rollout did not replace any pods' >&2;exit 3;fi
echo 'PASS: rolling restart replaced pods under maxUnavailable=1 and maxSurge=1'
pod="$($k -n "$ns" get pods -l app=metadata -o jsonpath='{.items[0].metadata.name}')"
"$k" -n "$ns" delete pod "$pod" --wait=false
"$k" -n "$ns" rollout status deployment/metadata --timeout=180s
for i in $(seq 1 35);do
 n="$($k -n "$ns" get pods -l app=metadata -o jsonpath='{.items[*].metadata.name}')"
 case " $n " in *" $pod "*) sleep 2;; *) break;; esac
done
k8s/rebalance.sh
k8s/check.sh
echo 'PASS: Kubernetes ReplicaSet replaced a deleted Pod and restored all 6 Service endpoints'
"$k" -n "$ns" scale deployment/metadata --replicas=9
trap '"$k" -n "$ns" scale deployment/metadata --replicas=6 >/dev/null' EXIT INT TERM
"$k" -n "$ns" rollout status deployment/metadata --timeout=180s
n="$($k -n "$ns" get pods -l app=metadata -o jsonpath='{range .items[*]}{.status.phase}{" "}{end}')"
echo "MANUAL SCALE RESULT: $n"
"$k" -n "$ns" scale deployment/metadata --replicas=6
"$k" -n "$ns" rollout status deployment/metadata --timeout=180s
trap - EXIT INT TERM
k8s/rebalance.sh
k8s/check.sh
echo 'PASS: manual scale-out and restoration. This is NOT an HPA automatic-scaling test.'
