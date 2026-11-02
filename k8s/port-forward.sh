#!/usr/bin/env bash
# Scope a local Gateway port-forward to this repository and preserve its PID.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p evidence
k="$PWD/Data/bin/kubectl"
config="$PWD/Data/kind-kubeconfig"
pidfile=evidence/kind-port-forward.pid
if [ -f "$pidfile" ]; then
  oldpid="$(cat "$pidfile")"
  if [ -n "$oldpid" ] && [ -r "/proc/$oldpid/cmdline" ]; then
    cmd="$(tr '\0' ' ' < "/proc/$oldpid/cmdline")"
    case "$cmd" in
      *port-forward*svc/gateway*28084:8080*)
        echo "Replacing previous repository-scoped port-forward (PID=$oldpid)"
        kill -TERM "$oldpid" || true
        sleep 1
        ;;
      *)
        echo "Prior PID $oldpid belongs to another process; refusing to stop it" >&2
        exit 4
        ;;
    esac
  fi
fi
# Do not steal a port from a different application.
if python3 - <<'PY'
import socket
s=socket.socket();s.settimeout(1)
try:
    s.connect(('127.0.0.1',28084));exit(0)
except OSError:
    exit(1)
finally:
    s.close()
PY
then
  echo 'Port 28084 is in use by another process; no new forward started' >&2
  exit 5
fi

nohup "$k" --kubeconfig "$config" -n oncall-lab port-forward --address 127.0.0.1 svc/gateway 28084:8080 > evidence/kind-port-forward.log 2>&1 < /dev/null &
echo "$!" > "$pidfile"
for i in $(seq 1 30); do
  if curl --noproxy '*' -fsS --max-time 3 'http://127.0.0.1:28084/metadata?id=kind-port-forward-check' > /dev/null; then
    echo 'PASS: scoped localhost:28084 -> Kubernetes Gateway -> real Kitex Metadata'
    exit 0
  fi
  sleep 1
done
echo 'Kind Gateway port-forward could not serve a real RPC request' >&2
tail -18 evidence/kind-port-forward.log >&2
exit 6
