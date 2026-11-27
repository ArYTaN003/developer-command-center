#!/usr/bin/env bash
# End-to-end smoke test against the local Compose stack (via the NGINX gateway).
# Usage:  ./scripts/smoke-test.sh          (gateway at http://localhost:8080)
set -euo pipefail
BASE="${BASE:-http://localhost:8080}"

echo "== Health =="
for p in github rag reviews notify; do
  printf "  /api/%s/health -> " "$p"
  curl -fsS "${BASE}/api/${p}/health" && echo
done

echo "== Simulate a PR (github-service) =="
curl -fsS -X POST "${BASE}/api/github/simulate/pr" \
  -H 'content-type: application/json' \
  -d '{"repo":"myorg/backend","number":142,"title":"Async handler refactor","author":"dev","body":"Switch sync handlers to async."}' && echo

echo "== Wait for async indexing + review =="
sleep 4

echo "== RAG context =="
curl -fsS "${BASE}/api/rag/context?repo=myorg/backend" && echo

echo "== Recent reviews =="
curl -fsS "${BASE}/api/reviews/reviews/recent" && echo

echo "== Trigger digest =="
curl -fsS -X POST "${BASE}/api/notify/digest/trigger" && echo
echo "== Latest digest =="
curl -fsS "${BASE}/api/notify/digest/latest" && echo
