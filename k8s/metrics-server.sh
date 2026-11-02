#!/usr/bin/env bash
# Metrics Server for this disposable Kind cluster only.
# KIND-ONLY --kubelet-insecure-tls is deliberately NOT suitable for production.
set -euo pipefail
cd "$(dirname "$0")/.."
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
k="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
mkdir -p Data
file=Data/metrics-server-components-v0.9.1.yaml
if [ ! -s "$file" ]; then
  curl -fsSL --retry 2 --max-time 90 \
    'https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.1/components.yaml' -o "$file"
fi
printf '%s  %s\n' '3c7f57cdbee0f57fb0259a150e8f6d6cb4f29d72d1aa5dce8803151dd6d4c2a1' "$file" | sha256sum -c -
"$k" apply -f "$file"
if ! "$k" -n kube-system get deploy metrics-server -o jsonpath='{.spec.template.spec.containers[0].args}' | grep -q -- '--kubelet-insecure-tls'; then
  "$k" -n kube-system patch deployment metrics-server --type=json \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
fi
"$k" -n kube-system rollout status deployment/metrics-server --timeout=180s
for i in $(seq 1 30); do
  if "$k" top nodes >/dev/null 2>&1;then
    echo 'PASS: metrics-server can read real Kind node resource metrics'
    "$k" top nodes
    exit 0
  fi
  sleep 3
done
"$k" -n kube-system logs deployment/metrics-server --tail=25
exit 2
