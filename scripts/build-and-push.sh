#!/usr/bin/env bash
# Build all 4 service images and push them to Docker Hub with a version tag.
# You run this manually (image creation + push is done by you).
#
# Usage:
#   DOCKERHUB_USER=yourname VERSION=1.0.0 ./scripts/build-and-push.sh
set -euo pipefail

DOCKERHUB_USER="${DOCKERHUB_USER:-YOUR_DOCKERHUB_USER}"
VERSION="${VERSION:-1.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SERVICES=(github-service rag-context-service ai-review-service notification-service)

if [[ "$DOCKERHUB_USER" == "YOUR_DOCKERHUB_USER" ]]; then
  echo "Set DOCKERHUB_USER to your Docker Hub username first." >&2
  exit 1
fi

for svc in "${SERVICES[@]}"; do
  img="${DOCKERHUB_USER}/${svc}:${VERSION}"
  echo "==> Building ${img}"
  docker build -t "${img}" "${ROOT}/services/${svc}"
  echo "==> Pushing ${img}"
  docker push "${img}"
done

echo "Done. Update image tags in k8s/services/*.yaml to ${DOCKERHUB_USER}/<svc>:${VERSION}"
echo "Tip:  grep -rl YOUR_DOCKERHUB_USER k8s | xargs sed -i '' \"s|YOUR_DOCKERHUB_USER|${DOCKERHUB_USER}|g\"   # macOS"
