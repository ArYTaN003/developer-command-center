# CLAUDE.md — Developer Command Center

Project context, operational notes, remaining work, and an explanation of the
notification/digest behaviour.

---

## 1. What this project is

A **Developer Command Center** — a 4-service microservices platform that fixes a real
daily problem for a developer working across many repos: **context loss, manual PR
tracking, and repetitive code-review triage**. It ingests GitHub activity, indexes it,
generates AI code-review summaries, and produces a daily digest — over a decoupled,
message-driven architecture.

- **Domain:** developer productivity / enterprise multi-project engineering.
- **Core principle (one line):** *Single Responsibility + Loose Coupling via Asynchronous
  Messaging.* Each service owns one concern and one data store; services talk through a
  RabbitMQ topic exchange; the only synchronous dependency is
  `ai-review-service → rag-context-service GET /context`.

---

## 2. The four services

| # | Service | Responsibility | Tech | Data store | Key endpoints |
|---|---|---|---|---|---|
| 1 | `github-service` | Ingest GitHub PRs/issues/commits; publish events | FastAPI, httpx, aio-pika, SQLAlchemy | PostgreSQL `github-db` | `/health`, `/poll`, `/webhook`, `/simulate/pr`, `/repos`, `/breaker` |
| 2 | `rag-context-service` | Index documents; answer context queries | FastAPI, Qdrant, Redis, aio-pika | Qdrant + Redis | `/health`, `/context`, `/session-start`, `/index` |
| 3 | `ai-review-service` | Generate AI review summaries | FastAPI, Anthropic SDK, pybreaker | PostgreSQL `reviews-db` | `/health`, `/reviews/trigger`, `/reviews/recent`, `/templates`, `/breaker`, `/debug/claude-fail` |
| 4 | `notification-service` | Activity feed + daily digest | FastAPI, Redis, APScheduler | Redis | `/health`, `/digest/trigger`, `/digest/latest`, `/activity` |

### Communication
| From → To | Style | Sync/Async | Why | On failure |
|---|---|---|---|---|
| github-service → GitHub API | REST (httpx) | Sync | Need live data | Circuit breaker trips |
| github-service → RabbitMQ | AMQP publish | Async | Decouple ingest from consumers | Events queued; consumers retry |
| RabbitMQ → rag / ai / notify | AMQP consume | Async | Work can lag; stay independent | NACK → requeue |
| ai-review → rag-context `/context` | REST GET | Sync | Review needs context now | Breaker → degraded review |
| ai-review → Claude | REST (SDK) | Sync | Core action | Breaker (fail_max=2, reset 10s) → fallback string |
| Client → Gateway → services | REST | Sync | Standard API access | 503; K8s replaces pod |

### Architectural components (all four present; at least two recommended)
- **API Gateway** — NGINX (Compose) / Ingress (K8s). Also serves the dashboard at `/`.
- **Message Queue** — RabbitMQ `github.events` topic exchange, 3 consumers.
- **Circuit Breaker** — pybreaker around Claude (`fail_max=2, reset_timeout=10s`) and RAG.
- **Service Registry** — Kubernetes DNS (services resolve by name).

---

## 3. How to run (local)

```bash
# Start Docker Desktop first and wait for the whale icon to be steady.
cd /path/to/developer-command-center
docker compose down -v        # ALWAYS: avoids the DB password/volume drift crash (see §6)
docker compose up -d --build  # 2× Postgres, Redis, Qdrant, RabbitMQ, gateway + 4 services
```
- **Dashboard:** <http://localhost:8080/>  (click-button UI, human-readable results)
- **RabbitMQ UI:** <http://localhost:15672>  (guest/guest)
- Stop: `docker compose down`  (add `-v` to wipe data).

### Credentials model
- **GitHub:** set a fallback `GITHUB_TOKEN` in `.env` for live polling, or drive the pipeline
  locally with no token via `/webhook` and `/simulate/*`.
- **Claude:** standard Anthropic config, read from the `.env` **file** (via `env_file:`) so an
  ambient shell `ANTHROPIC_BASE_URL` can't override it:
  - `ANTHROPIC_API_KEY=<your key>`
  - `ANTHROPIC_BASE_URL=https://api.anthropic.com`  (only change if you use a compatible proxy)
  - `CLAUDE_MODEL=claude-haiku-4-5`  (or another model your key can access)
- Everything degrades to **local stubs** if no key is set, so the pipeline always runs.

---

## 4. Repository layout

```
docker-compose.yml        # full local stack (uses env_file: .env for Claude config)
.env / .env.example       # config; .env is git-ignored and holds real secrets
CONFIGURATION.md          # which values to provide + how to get each
nginx/nginx.conf          # gateway: serves dashboard at / + routes /api/* (proxy_read_timeout 300s)
web/index.html            # the dashboard (mounted into the gateway)
Jenkinsfile               # reference CI/CD pipeline (not auto-wired)
services/<svc>/           # Dockerfile (multi-stage python:3.12-slim-bookworm), requirements, app/
k8s/                      # namespace, configmap, secrets, infra (StatefulSets+PVC), services, ingress
jenkins/                  # optional Jenkins-as-code (credentials via placeholders)
scripts/                  # build-and-push, minikube-setup, smoke-test, circuit-breaker-demo
```

---

## 5. Architecture decisions
- **AD-1** RabbitMQ over Kafka — low volume, simple topology, small Minikube footprint.
- **AD-2** Qdrant over ChromaDB — payload filtering, small image, production-ready.
- **AD-3** Python/FastAPI over Spring Boot — native AI ecosystem (Anthropic SDK), fast build.
- **AD-4** pybreaker — Python-native breaker with full CLOSED/OPEN/HALF-OPEN state machine.

---

## 6. Operational gotchas learned
1. **DB password / volume drift →** `github-service`/`ai-review-service` crash with
   `InvalidPasswordError`. Postgres only sets the password on first volume init, so kept
   volumes drift from `.env`. **Always start with `docker compose down -v`.**
2. **Editing a bind-mounted file** (e.g. `nginx/nginx.conf`, `web/index.html`) swaps its
   inode and breaks the mount → **recreate that container** (`up -d --force-recreate gateway`).
   (`web/index.html` content edits are fine — only matters if the file is replaced.)
3. **504 on AI calls** was nginx's default 60s timeout — raised to **300s** in `nginx.conf`.
4. **Truncated reviews** were from `max_tokens` — fixed by a **bounded prompt** +
   a higher `max_tokens` + an explicit "hit the cap" marker.
5. **Claude config must come from the `.env` file** (`env_file:`) — if a shell exports
   `ANTHROPIC_BASE_URL`, reading from the file prevents it from overriding the intended value.

---

## 7. Remaining work (roadmap)

**Deployment / infra**
- Push images to a registry with version tags and reference those tags in the K8s manifests
  (replace the `YOUR_DOCKERHUB_USER` placeholder). `./scripts/build-and-push.sh` helps.
- Deploy to a Kubernetes cluster (`./scripts/minikube-setup.sh`), fill in `k8s/secrets.yaml`,
  apply `namespace → configmap/secrets → infrastructure → services → ingress`; verify all pods
  `Running` and all PVCs `Bound`.

**Resilience / features (see the per-service task notes kept locally)**
- Dead-letter queue + retry cap on all consumers; make review generation idempotent.
- gRPC path alongside the REST `/context` call; full CRUD (PUT/DELETE) on templates/repos.
- Un-block the async consumer (run blocking HTTP/SDK calls off the event loop).
- Webhook HMAC verification; guard the mutating/debug endpoints.
- Optional: semantic embeddings (`EMBEDDING_MODE=st`), Slack delivery, Prometheus metrics.

**Demos to capture**
- Circuit breaker: healthy → stop dependency → breaker opens → fallback → recovery.
- K8s self-healing: `kubectl delete pod <rag-context-service pod>` → ReplicaSet restores
  count=2 while the other replica serves traffic.

---

## 8. Notification & Digest — why you see "no notification"

**This is expected — the service is pull-based, not push-based.** Here's exactly what it
does and does not do.

### What `notification-service` actually does
1. **Consumes events** off RabbitMQ (`pr.opened`, `pr.closed`, `commit.pushed`,
   `issue.created`) and records them in a Redis **activity feed**, de-duplicated via a Redis
   set. → visible at `GET /api/notify/activity`.
2. **Builds a digest** — aggregates recent activity + recent AI reviews and asks Claude to
   write a ~200-word morning brief. It is **stored in Redis** and returned by
   `GET /api/notify/digest/latest` (it does **not** write a file or push anywhere).
3. **Schedules** the digest **once a day at 08:00 UTC** via APScheduler.

### Why nothing "arrives"
- **There is no delivery channel** (no Slack, email, browser push, or OS notification). The
  app's "notification" = data you **retrieve** (dashboard, or the `/digest` and `/activity`
  endpoints). It never pushes to you.
- **The only automatic trigger is the 08:00 UTC cron** — so unless you're running at ~08:00
  UTC, nothing generates on its own.
- **The feed is empty until events flow.** If you haven't simulated/ingested a PR, there's no
  activity and the digest is empty.

### What to do to "get a notification" right now
1. **Simulate PR** (or ingest from a connected repo) so events flow. Optionally trigger a
   review so the digest has reviews too.
2. **Generate digest** (`POST /api/notify/digest/trigger`) — builds it now instead of waiting
   for 08:00 UTC.
3. Read **Latest digest** / **Recent activity**.

### To get REAL push notifications (optional enhancement)
Add a delivery channel to `notification-service`, e.g. a **Slack incoming webhook** (set
`SLACK_WEBHOOK_URL` in `.env`, send on each alert event and on digest generation), **email
(SMTP)**, a **browser push / WebSocket** feed into the dashboard, or a shorter cron interval
for a live run.
