#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p Data/bin evidence
export KUBECONFIG="$PWD/Data/kind-kubeconfig"
CLUSTER=oncall-lab-kind
KIND="$(go env GOPATH)/bin/kind"
if [ ! -x "$KIND" ]; then
  echo 'Installing pinned Kind v0.33.0 locally via go install'
  go install sigs.k8s.io/kind@v0.33.0
fi
KUBECTL="${KUBECTL_BIN:-$PWD/Data/bin/kubectl}"
if [ ! -x "$KUBECTL" ]; then
  # Download a matching public Kubernetes CLI; never modify system kubectl.
  url='https://dl.k8s.io/release/v1.34.11/bin/linux/amd64/kubectl'
  curl -fsSL --retry 2 --max-time 120 "$url" -o Data/bin/kubectl
  curl -fsSL --retry 2 --max-time 40 "$url.sha256" -o Data/bin/kubectl.sha256
  printf '%s  %s\n' "$(cat Data/bin/kubectl.sha256)" Data/bin/kubectl | sha256sum -c -
  chmod 0755 Data/bin/kubectl
fi
echo 'Building the actual local Kitex images BEFORE loading into Kind'
docker compose build metadata gateway
existing_cluster=false
if "$KIND" get clusters | grep -Fxq "$CLUSTER"; then
  existing_cluster=true
else
  # Official pinned Kind node image, all simulated zones on the same machine.
  "$KIND" create cluster --name "$CLUSTER" --config k8s/kind.yaml \
    --image kindest/node:v1.34.11@sha256:44e222ee2132dab25ff87301682f89eb82c7880ea3a1bf543bfe9708fd08d67d \
    --kubeconfig "$KUBECONFIG" --wait 180s
fi
# Recover scoped kubeconfig if the Kind nodes survived a local data cleanup.
if [ ! -s "$KUBECONFIG" ]; then
  "$KIND" export kubeconfig --name "$CLUSTER" --kubeconfig "$KUBECONFIG"
fi
"$KUBECTL" config use-context "kind-$CLUSTER" >/dev/null
for entry in "worker:a" "worker2:b" "worker3:c"; do
  node="${entry%%:*}"
  zone="${entry##*:}"
  "$KUBECTL" label node "$CLUSTER-$node" topology.kubernetes.io/zone="lab-zone-$zone" --overwrite
  echo "$CLUSTER-$node -> lab-zone-$zone"
done
"$KIND" load docker-image oncall-lab-metadata:local --name "$CLUSTER"
"$KIND" load docker-image oncall-lab-gateway:local --name "$CLUSTER"
"$KUBECTL" apply -f k8s/manifests.yaml
# Kind nodes can cache an older image tagged :local. On repeat runs, restart
# workloads to pick up the newly loaded image. On first boot, no restart needed.
if [ "$existing_cluster" = true ]; then
  "$KUBECTL" -n oncall-lab rollout restart deploy/metadata deploy/gateway
fi
"$KUBECTL" -n oncall-lab rollout status deploy/metadata --timeout=240s
"$KUBECTL" -n oncall-lab rollout status deploy/gateway --timeout=240s
KUBECTL_BIN="$KUBECTL" k8s/rebalance.sh
KUBECTL_BIN="$KUBECTL" k8s/check.sh
"$KUBECTL" -n oncall-lab get pods -o wide
printf '\nKind context is scoped to: %s\n' "$KUBECONFIG"
