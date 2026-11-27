#!/usr/bin/env bash
# Start Minikube with the resources this stack needs and enable addons.
set -euo pipefail

minikube start --driver=docker --cpus=4 --memory=8192 --disk-size=30g
minikube addons enable ingress
minikube addons enable metrics-server

echo
echo "Minikube ready. Next:"
echo "  1) (optional) build images into Minikube's docker:  eval \$(minikube docker-env) && DOCKERHUB_USER=local ./scripts/build-and-push-local.sh"
echo "  2) kubectl apply -f k8s/namespace.yaml"
echo "  3) kubectl apply -f k8s/configmap.yaml -f k8s/secrets.yaml"
echo "  4) kubectl apply -f k8s/infrastructure/"
echo "  5) kubectl apply -f k8s/services/"
echo "  6) kubectl apply -f k8s/ingress/ingress.yaml"
echo "  7) echo \"\$(minikube ip)  dcc.local\" | sudo tee -a /etc/hosts"
