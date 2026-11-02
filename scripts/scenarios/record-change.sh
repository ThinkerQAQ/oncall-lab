#!/usr/bin/env bash
# Record an actual container recreation, not a fabricated code release.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p evidence
stamp="$(date +%Y%m%d-%H%M%S)"
python3 scripts/capture_changes.py "evidence/deploy-before-$stamp.json"
# Only touch the dedicated synthetic gateway instance.
docker compose -f compose.yaml -f compose.zones.yaml up -d --no-deps --no-build --force-recreate gateway-zone-c2
python3 scripts/capture_changes.py "evidence/deploy-after-$stamp.json"
python3 - "evidence/deploy-before-$stamp.json" "evidence/deploy-after-$stamp.json" <<'PY'
import json,sys
before=json.load(open(sys.argv[1]))['services']
after=json.load(open(sys.argv[2]))['services']
assert before['gateway-zone-c2']['container'] == after['gateway-zone-c2']['container']
assert before['gateway-zone-c2']['started_at'] != after['gateway-zone-c2']['started_at']
assert before['gateway-zone-c2']['image_id'] == after['gateway-zone-c2']['image_id']
for name in before:
 if name!='gateway-zone-c2':
  assert before[name]['image_id']==after[name]['image_id']
print('PASS: real gateway-zone-c2 container recreated with the same image; not a code deployment')
PY
