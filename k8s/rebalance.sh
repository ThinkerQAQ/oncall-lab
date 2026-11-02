#!/usr/bin/env bash
# Pod topology spread constraints are placement constraints, not a rebalance daemon.
# If a rolling update ends 3/2/1, replace one Pod in the overfull zone.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
for round in 1 2 3; do
  "$k" get nodes -o json > evidence/kind-nodes.json
  "$k" -n oncall-lab get pods -l app=metadata -o json > evidence/kind-metadata-pods.json
  pod="$(python3 - <<'PY'
import json,collections
nodes=json.load(open('evidence/kind-nodes.json'))['items']
pods=json.load(open('evidence/kind-metadata-pods.json'))['items']
labels={x['metadata']['name']:x['metadata'].get('labels',{}).get('topology.kubernetes.io/zone') for x in nodes}
items=[p for p in pods if not p['metadata'].get('deletionTimestamp')]
by_zone=collections.defaultdict(list)
for p in items:by_zone[labels[p['spec']['nodeName']]].append(p['metadata']['name'])
counts={z:len(by_zone[z]) for z in ['lab-zone-a','lab-zone-b','lab-zone-c']}
print('balanced' if all(x==2 for x in counts.values()) else by_zone[max(counts,key=counts.get)][-1])
print('Zone counts:',counts,file=__import__('sys').stderr)
PY
)"
  if [ "$pod" = balanced ]; then echo 'All three logical zones have 2 real Metadata Pods';exit 0;fi
  echo "Replacing $pod to converge synthetic placement"
  "$k" -n oncall-lab delete pod "$pod" --wait=false
  "$k" -n oncall-lab rollout status deployment/metadata --timeout=120s
  sleep 4
done
k8s/check.sh
