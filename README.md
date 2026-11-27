<div align="center">

# 🧭 Developer Command Center

**A four-service microservices platform that kills context-loss for developers juggling many ERP/software projects.**

It ingests GitHub activity, indexes it for retrieval, generates AI code-review summaries, and ships a daily digest — all over a decoupled, message-driven architecture.

<br/>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Minikube-326CE5?logo=kubernetes&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600?logo=rabbitmq&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-v1.12-DC244C)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)

<sub>Microservices platform · runs fully locally</sub>

</div>

---

> [!TIP]
> **Zero-config quick start:** `cp .env.example .env && docker compose up --build`
> Every external call (GitHub, Claude) falls back to a local stub, so the whole pipeline
> runs with **no credentials**. Add keys only when you want live data — see [Configuration](CONFIGURATION.md).

## 📑 Contents

- [Core principle](#-core-principle)
- [Architecture at a glance](#-architecture-at-a-glance)
- [The four services](#-the-four-services)
- [Communication](#-communication)
- [Architectural components](#-architectural-components)
- [Placeholders](#-placeholders)
- [Run locally](#-run-locally)
- [Failure demos](#-failure-demos)
- [Deploy to Kubernetes](#-deploy-to-kubernetes-minikube)
- [Repository layout](#-repository-layout)
- [Architecture decisions](#-architecture-decisions)

---

## 🎯 Core principle

> **Single Responsibility + Loose Coupling via Asynchronous Messaging.**

Each service owns **one concern** and **one data store**. Services talk through a RabbitMQ
topic exchange, so producers never know their consumers. The **only** synchronous dependency
is `ai-review-service → rag-context-service GET /context` — justified because a review can't
be generated without project context.

It's proven two ways: the **circuit breaker** (Claude) and **Kubernetes self-healing**
(`rag-context-service`, 2 replicas).

---

## 🏗 Architecture at a glance

<div align="center">
  <sub>Architecture overview (ASCII view below).</sub>
</div>

<details>
<summary><b>Text view (ASCII)</b></summary>

```text
                                 ┌──────────────────────────────┐
   Developer / API client ──────▶│   API Gateway (NGINX / Ingress)
                                 └───────────────┬──────────────┘
          /api/github  /api/rag  /api/reviews  /api/notify
                 │          │          │             │
                 ▼          ▼          ▼             ▼
        ┌───────────────┐  ┌───────────────────┐  ┌──────────────────┐  ┌──────────────────────┐
        │ github-service│  │ rag-context-service│  │ ai-review-service │  │ notification-service │
        │  Postgres     │  │  Qdrant + Redis    │  │  Postgres         │  │  Redis               │
        └───────┬───────┘  └─────────▲─────────┘  └───────┬──────────┘  └──────────▲───────────┘
                │ publish            │ GET /context (sync) │                        │
                ▼                    └─────────────────────┘                        │
        ┌───────────────────────────────── RabbitMQ (topic: github.events) ────────┘
                  async fan-out ▶ rag · ai-review · notification
```

**Legend** — `──▶` sync REST · RabbitMQ edges are async publish/consume · each service has its own data store.

</details>

---

## 🧩 The four services

| # | Service | Responsibility | Tech stack | Data store | Key endpoints |
|:-:|---|---|---|---|---|
| 1 | **`github-service`** | Ingest GitHub activity & publish events | FastAPI · httpx · aio-pika · SQLAlchemy | PostgreSQL `github-db` | `/health` · `/webhook` · `/simulate/pr` · `/repos` · `/breaker` |
| 2 | **`rag-context-service`** | Index documents & answer context queries | FastAPI · Qdrant · Redis · aio-pika | Qdrant + Redis | `/health` · `/context` · `/session-start` · `/index` |
| 3 | **`ai-review-service`** | Generate AI review summaries | FastAPI · Anthropic SDK · pybreaker | PostgreSQL `reviews-db` | `/health` · `/reviews/trigger` · `/reviews/{pr_id}` · `/templates` · `/breaker` |
| 4 | **`notification-service`** | Daily digest + alert dedup | FastAPI · Redis · APScheduler | Redis | `/health` · `/digest/trigger` · `/digest/latest` · `/activity` |

---

## 🔌 Communication

| From → To | Style | Sync/Async | Why | On failure |
|---|:-:|:-:|---|---|
| github-service → GitHub API | REST (httpx) | 🟦 Sync | Need live data | Circuit breaker trips |
| github-service → RabbitMQ | AMQP publish | 🟧 Async | Decouple ingest from consumers | Events queued; consumers retry |
| RabbitMQ → rag / ai / notify | AMQP consume | 🟧 Async | Work can lag; stay independent | NACK → requeue |
| ai-review-service → rag-context-service | REST GET | 🟦 Sync | Review needs context now | Breaker → degraded review |
| ai-review-service → Claude API | REST (SDK) | 🟦 Sync | Core action, result needed now | Breaker → fallback string |
| Client → Gateway → services | REST | 🟦 Sync | Standard API access | 503; K8s replaces pod |

---

## 🛠 Architectural components

| Component | Implementation | What it shows |
|---|---|---|
| 🚪 **API Gateway** | NGINX (Compose) / Ingress (K8s) | Single entry point, path-prefix routing |
| 📨 **Message Queue** | RabbitMQ `github.events` topic exchange | One producer, three consumers |
| ⚡ **Circuit Breaker** | pybreaker (Claude `fail_max=2, reset_timeout=10s`; RAG) | CLOSED → OPEN → HALF-OPEN → CLOSED |
| 🧭 **Service Registry** | Kubernetes DNS | Services resolve by name, not IP |

---

## 🔑 Placeholders

> [!NOTE]
> The project runs end-to-end with **no real credentials** — external calls degrade to local
> stubs. Full step-by-step for each value lives in **[CONFIGURATION.md](CONFIGURATION.md)**.

| Placeholder | Where | Behaviour when left as a placeholder |
|---|---|---|
| `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` | `.env`, K8s Secret | Claude calls return a local stub summary/review |
| `GITHUB_TOKEN`, `GITHUB_API_URL` | `.env`, K8s ConfigMap/Secret | Polling off; drive via `/webhook` + `/simulate` |
| DB passwords (`*_DB_PASSWORD`) | `.env`, K8s Secret | Compose uses working defaults; set real values in K8s |
| `YOUR_DOCKERHUB_USER` | `k8s/services/*.yaml`, `Jenkinsfile`, scripts | Replace before building/pushing images |

Image build/push and cluster wiring are done **manually by you** (see the scripts below).

---

## 🚀 Run locally

```bash
cp .env.example .env          # optional: add a real Claude key / GitHub token
docker compose up --build     # 2× Postgres, Redis, Qdrant, RabbitMQ, gateway + 4 services
```

| Endpoint | URL |
|---|---|
| 🚪 API Gateway | <http://localhost:8080> → `/api/github/*` · `/api/rag/*` · `/api/reviews/*` · `/api/notify/*` |
| 🐰 RabbitMQ Management UI | <http://localhost:15672> · `guest` / `guest` |

**One-shot smoke test of the whole pipeline:**

```bash
./scripts/smoke-test.sh
```

<details>
<summary><b>Manual walk-through (curl)</b></summary>

```bash
# 1) produce a PR event (no GitHub token needed)
curl -X POST http://localhost:8080/api/github/simulate/pr \
  -H 'content-type: application/json' \
  -d '{"repo":"myorg/backend","number":142,"title":"Async handler refactor","body":"..."}'

# 2) query project context (RAG)
curl "http://localhost:8080/api/rag/context?repo=myorg/backend"

# 3) see the AI review generated from the pr.opened event
curl "http://localhost:8080/api/reviews/reviews/recent"

# 4) generate + read the daily digest
curl -X POST http://localhost:8080/api/notify/digest/trigger
curl http://localhost:8080/api/notify/digest/latest
```

</details>

Stop everything with `docker compose down` (add `-v` to wipe data volumes).

---

## 🔥 Failure demos

### ⚡ (a) Circuit breaker — `fail_max=2, reset_timeout=10s`

```bash
./scripts/circuit-breaker-demo.sh
```

```text
CLOSED ──▶ 2 failures ──▶ OPEN ──▶ fallback returned ──▶ wait 10s ──▶ HALF-OPEN ──▶ CLOSED
```

Works **without a real Claude key** via the `/debug/claude-fail` toggle.
Watch the state live: `curl http://localhost:8080/api/reviews/breaker`.

### 🩹 (b) Kubernetes self-healing — `rag-context-service` (2 replicas)

```bash
kubectl get pods -n microservices -w                             # terminal 1
kubectl delete pod <rag-context-service-pod> -n microservices    # terminal 2
```

The replacement pod starts automatically while the second replica keeps serving traffic —
the Deployment's ReplicaSet restores the desired count (2).

---

## ☸️ Deploy to Kubernetes (Minikube)

```bash
./scripts/minikube-setup.sh                   # start Minikube + addons

# ── Option A: build into Minikube's Docker daemon (no registry) ──
eval $(minikube docker-env)
DOCKERHUB_USER=local ./scripts/build-and-push-local.sh
#   then set image tags in k8s/services/*.yaml to local/<svc>:1.0.0

# ── Option B: push to Docker Hub, then reference the tags ──
DOCKERHUB_USER=yourname ./scripts/build-and-push.sh

# ── Apply manifests in order ──
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml -f k8s/secrets.yaml    # edit secrets first
kubectl apply -f k8s/infrastructure/
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress/ingress.yaml
echo "$(minikube ip)  dcc.local" | sudo tee -a /etc/hosts
```

✅ **Verify:** `kubectl get pods -n microservices` (all `Running`) · `kubectl get pvc -n microservices` (all `Bound`).

> CI/CD is optional and reference-only — see [`jenkins/README.md`](jenkins/README.md).

---

## 📁 Repository layout

```text
.
├── docker-compose.yml       # full local stack (one command)
├── .env.example             # all config keys (placeholders)
├── CONFIGURATION.md         # which values to provide + how to get each
├── nginx/nginx.conf         # API gateway for Compose
├── Jenkinsfile              # reference CI/CD pipeline (not auto-wired)
├── services/<svc>/          # Dockerfile · requirements.txt · app/
├── k8s/                     # namespace · config · secrets · infra · services · ingress
├── jenkins/                 # optional Jenkins-as-code (credentials via placeholders)
└── scripts/                 # build/push · minikube-setup · smoke-test · circuit-breaker-demo
```

---

## 🧠 Architecture decisions

| # | Decision | Why |
|:-:|---|---|
| **AD-1** | RabbitMQ over Kafka | Low event volume, simple topology, small Minikube footprint |
| **AD-2** | Qdrant over ChromaDB | Strong payload filtering, small image, production-ready |
| **AD-3** | Python / FastAPI over Spring Boot | Native AI ecosystem (Anthropic SDK), fast to build |
| **AD-4** | pybreaker | Python-native breaker with a full CLOSED/OPEN/HALF-OPEN state machine |

<details>
<summary><b>Dockerfile base-image justification</b></summary>

`python:3.12-slim-bookworm` (not alpine): C-extension wheels (`asyncpg`, Qdrant client) need
glibc; alpine's musl causes wheel build failures and far slower builds. The multi-stage build
keeps compilers out of the runtime image (~40% smaller), runs as a non-root user, and defines
a `/health` HEALTHCHECK.

</details>

---

<div align="center"><sub>Runs locally · <a href="CONFIGURATION.md">configure credentials</a></sub></div>
