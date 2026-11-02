#!/usr/bin/env bash
# Reproduce real Grafana -> SMTP -> Mailpit firing and resolved emails.
# All traffic is synthetic and all email is captured locally.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p evidence
stamp="$(date +%Y%m%d-%H%M%S)"
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
compose=(docker compose -f compose.yaml -f compose.zones.yaml)

# Build services for first-time use; subsequent runs reuse Docker build cache.
"${compose[@]}" build metadata gateway loadgen

# Only operates on oncall-lab Compose services, not other projects.
"${compose[@]}" up -d mailpit prometheus grafana \
  metadata-zone-a1 metadata-zone-a2 metadata-zone-b1 metadata-zone-b2 metadata-zone-c1 metadata-zone-c2 \
  gateway-zone-a1 gateway-zone-a2 gateway-zone-b1 gateway-zone-b2 gateway-zone-c1 gateway-zone-c2

for i in $(seq 1 30); do
  if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:28025/api/v1/info >/dev/null && \
     curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:23000/api/health >/dev/null && \
     curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:28081/healthz >/dev/null;then
    break
  fi
  sleep 2
done
log="evidence/alert-notification-$stamp.log"
echo "Sending real synthetic Kitex requests, then recovering. Local evidence: $log"
"${compose[@]}" run --rm --no-deps \
  -e SCENARIO=zone-timeout \
  -e QPS=25 \
  -e BASELINE_SECONDS=12 \
  -e INCIDENT_SECONDS=55 \
  -e RECOVERY_SECONDS=35 \
  -e ZONE_A_FAIL_PERCENT=45 \
  loadgen-zones > "$log" 2>&1
python3 scripts/verify_zone_run.py "$log"
python3 scripts/verify_mailpit_notifications.py \
  --since "$since" --timeout 125 \
  --save "evidence/alert-notifications-$stamp.json"
echo "PASS: real fault -> Grafana FIRING email -> RESOLVED email."
echo "Mailpit inbox: http://127.0.0.1:28025"
