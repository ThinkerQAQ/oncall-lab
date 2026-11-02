#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
mkdir -p evidence
"$k" get nodes -o json > evidence/kind-nodes.json
"$k" -n oncall-lab get pods -l app=metadata -o json > evidence/kind-metadata-pods.json
"$k" -n oncall-lab get endpointslices -l kubernetes.io/service-name=metadata -o json > evidence/kind-metadata-endpoints.json
python3 k8s/check.py evidence/kind-nodes.json evidence/kind-metadata-pods.json evidence/kind-metadata-endpoints.json
