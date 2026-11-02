#!/usr/bin/env bash
# Reproducible real Kitex transport error. Target is restricted to lab zone-b1.
set -euo pipefail
cd "$(dirname "$0")/../.."
compose=(docker compose -f compose.yaml -f compose.zones.yaml)
backend=metadata-zone-b1
recovered=0
recover() {
  if [ "$recovered" -eq 0 ]; then
    echo "[RECOVERY] restoring ${backend}"
    "${compose[@]}" start "$backend" >/dev/null
    recovered=1
  fi
}
trap recover EXIT INT TERM

url='http://127.0.0.1:28082/metadata?id=transport-failure-test'
status=$(curl --noproxy '*' -sS --max-time 5 -o /dev/null -w '%{http_code}' "$url")
test "$status" = 200 || { echo "Preflight failed: expected 200, got $status"; exit 2; }
echo "[BASELINE] Kitex RPC HTTP=${status}"

"${compose[@]}" stop "$backend" >/dev/null
echo "[FAULT] backend ${backend} stopped; real socket connection should fail"
# A stopped Kitex server can first present a stale connection; retry briefly.
matched=0
for attempt in $(seq 1 6); do
  response=$(curl --noproxy '*' -sS --max-time 5 -o /dev/null -w '%{http_code}' "$url")
  echo "[FAULT] attempt=${attempt} HTTP=${response}"
  # Under the 1.2s RPC budget, Kitex may exhaust its connection retries
  # and surface an RPC timeout even when the real cause is DNS/transport.
  if [ "$response" = 504 ] || [ "$response" = 502 ]; then matched=1; break; fi
  sleep 1
done
if [ "$matched" -ne 1 ]; then echo 'Expected actual Kitex RPC failure after backend shutdown' >&2; exit 3; fi
transport_logged=0
for i in $(seq 1 10); do
  if docker logs --tail 80 oncall-lab-gateway-zone-b1-1 2>&1 | grep -Eq '(get connection error|remote or network error|connection refused)'; then
    transport_logged=1
    break
  fi
  sleep 1
done
if [ "$transport_logged" -ne 1 ]; then
  echo 'Backend was stopped but expected transport evidence was absent from Kitex logs' >&2
  exit 5
fi
echo '[EVIDENCE] Kitex logged a transport/connection failure, even though the final RPC may be classified as timeout'

recover
for i in $(seq 1 20); do
  status=$(curl --noproxy '*' -sS --max-time 5 -o /dev/null -w '%{http_code}' "$url" || true)
  if [ "$status" = 200 ]; then
    echo '[RECOVERY] Backend is online; real Kitex RPC HTTP=200'
    echo 'PASS: actual transport failure logged; final HTTP code depends on RPC budget and retry behavior'
    exit 0
  fi
  sleep 1
done
echo 'Backend did not recover to HTTP 200' >&2
exit 4
