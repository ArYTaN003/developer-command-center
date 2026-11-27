#!/usr/bin/env bash
# Build images directly into Minikube's Docker daemon (no registry needed).
# Run AFTER:  eval $(minikube docker-env)
# Then set image tags in k8s/services/*.yaml to local/<svc>:1.0.0 (imagePullPolicy: IfNotPresent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${DOCKERHUB_USER:-local}"
VERSION="${VERSION:-1.0.0}"
for svc in github-service rag-context-service ai-review-service notification-service; do
  echo "==> Building ${PREFIX}/${svc}:${VERSION} (into current docker daemon)"
  docker build -t "${PREFIX}/${svc}:${VERSION}" "${ROOT}/services/${svc}"
done
echo "Built. If using Minikube's daemon, images are available to the cluster directly."
