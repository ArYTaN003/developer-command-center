#!/usr/bin/env bash
# Circuit-breaker demo for ai-review-service (works with NO real Claude key).
# Config: fail_max=2, reset_timeout=10s (see .env / ConfigMap).
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"
REVIEWS="${BASE}/api/reviews"

say() { echo; echo "### $*"; }
state() { curl -fsS "${REVIEWS}/breaker" | python3 -m json.tool; }

say "1) Healthy — breaker CLOSED"
state

say "2) Force Claude failures ON"
curl -fsS -X POST "${REVIEWS}/debug/claude-fail?enabled=true" && echo

say "3) Trigger reviews until breaker OPENs (fail_max=2)"
for i in 1 2 3; do
  echo "-- review attempt $i --"
  curl -fsS -X POST "${REVIEWS}/reviews/trigger" \
    -H 'content-type: application/json' \
    -d "{\"repo\":\"myorg/backend\",\"number\":$((900+i)),\"title\":\"demo\"}" && echo
  state
done

say "4) Breaker should be OPEN -> fallback returned immediately (no Claude call)"
state

say "5) Fix Claude (force-fail OFF) and wait reset_timeout (10s)"
curl -fsS -X POST "${REVIEWS}/debug/claude-fail?enabled=false" && echo
sleep 11

say "6) Next review succeeds -> HALF-OPEN -> CLOSED (recovery)"
curl -fsS -X POST "${REVIEWS}/reviews/trigger" \
  -H 'content-type: application/json' \
  -d '{"repo":"myorg/backend","number":999,"title":"recovery"}' && echo
state
