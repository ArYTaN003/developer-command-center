# Configuration Values — What to Provide & How to Get Each

This project **runs locally with zero configuration** — every external call falls
back to a local stub. You only fill in values to (1) turn on real Claude output,
(2) turn on live GitHub ingest, (3) push images, or (4) deploy to Kubernetes / use
Jenkins.

There are **two** env files:

| File | Copy from | Used by |
|---|---|---|
| `.env` | `.env.example` | the application stack (`docker compose up`) |
| `jenkins/.env` | `jenkins/.env.example` | the optional Jenkins CI/CD setup |

```bash
cp .env.example .env
cp jenkins/.env.example jenkins/.env   # only if you use Jenkins
```

---

## Priority: do only what you need

| Goal | Values to set | Section |
|---|---|---|
| Just run the demo locally | **none** | — |
| Real AI review/summary output | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL` | [1](#1-claude--anthropic-api) |
| Live GitHub ingest (not simulate) | `GITHUB_TOKEN`, `GITHUB_REPOS`, `GITHUB_POLL_ENABLED` | [2](#2-github-api) |
| Custom DB / broker passwords | `*_DB_PASSWORD`, `RABBITMQ_PASSWORD` | [3](#3-database--rabbitmq-passwords) |
| Build & push images | `DOCKERHUB_USER` (+ `docker login`) | [4](#4-docker-hub) |
| Jenkins pipeline | `jenkins/.env` values | [5](#5-jenkins-credentials-optional) |

---

## 1. Claude / Anthropic API

**Values (in `.env`):**

| Key | Example | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Secret. Required for real AI output. |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Keep default unless given a proxy/gateway URL. |
| `CLAUDE_MODEL` | `claude-haiku-4-5` | Any model your key can access. |

**How to get the key — step by step:**
1. Open <https://console.anthropic.com> and sign in.
2. Left sidebar → **API Keys**.
3. Click **Create Key**, name it (e.g. `dcc-local`), **Create**.
4. **Copy the key immediately** (shown only once) → paste into `ANTHROPIC_API_KEY`.
5. Ensure your account has credit/billing enabled (Settings → Billing).
6. `ANTHROPIC_BASE_URL`: leave as the default. If you were handed a custom endpoint
   (internal proxy, gateway, Bedrock-style URL), paste that instead.

> Left as a placeholder → services return `[local-stub ...]` responses. The pipeline
> still works; it just isn't real AI text.

**For Kubernetes:** key goes in `k8s/secrets.yaml` (`ANTHROPIC_API_KEY`); URL and model
go in `k8s/configmap.yaml` (`ANTHROPIC_BASE_URL`, `CLAUDE_MODEL`).

---

## 2. GitHub API

**Values (in `.env`):**

| Key | Example | Notes |
|---|---|---|
| `GITHUB_TOKEN` | `github_pat_...` | Secret. Fine-grained PAT. |
| `GITHUB_API_URL` | `https://api.github.com` | Keep default (or GHE URL). |
| `GITHUB_REPOS` | `myorg/backend,myorg/api` | Comma-separated `owner/repo`. |
| `GITHUB_POLL_ENABLED` | `true` | Set `true` to auto-poll the repos. |

**How to get the token — step by step:**
1. GitHub → top-right avatar → **Settings**.
2. Bottom-left → **Developer settings**.
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
4. Name it, set an expiry.
5. **Repository access** → *Only select repositories* → choose your repo(s).
6. **Permissions → Repository permissions**, set each to **Read-only**:
   - **Contents**
   - **Pull requests**
   - **Issues**
7. **Generate token** → copy (`github_pat_...`) → paste into `GITHUB_TOKEN`.
8. Put the same repos in `GITHUB_REPOS` and set `GITHUB_POLL_ENABLED=true`.

> Left as a placeholder → polling stays off. You still drive the pipeline with:
> ```bash
> curl -X POST http://localhost:8080/api/github/simulate/pr \
>   -H 'content-type: application/json' \
>   -d '{"repo":"myorg/backend","number":142,"title":"Demo PR","body":"..."}'
> ```

**For Kubernetes:** token in `k8s/secrets.yaml` (`GITHUB_TOKEN`); repos/URL/flag in
`k8s/configmap.yaml`.

---

## 3. Database & RabbitMQ passwords

**Values (in `.env`):** `GITHUB_DB_PASSWORD`, `REVIEWS_DB_PASSWORD`, `RABBITMQ_PASSWORD`.

**How to get them:** You **choose** them — they are not obtained from any provider.
Generate a strong value with:
```bash
openssl rand -base64 16
```

- **Local (Compose):** safe defaults already exist (`github` / `reviews` / `guest`).
  You can leave these alone for the local demo.
- **Kubernetes:** set real values in `k8s/secrets.yaml`. The Postgres pods and the
  app pods read the *same* Secret keys, so they stay in sync automatically.

---

## 4. Docker Hub

**Value:** replace the literal `YOUR_DOCKERHUB_USER` wherever it appears
(`k8s/services/*.yaml`, `Jenkinsfile`, `scripts/build-and-push.sh`).

**How to get it — step by step:**
1. Open <https://hub.docker.com> → sign up / sign in.
2. Your **username** is top-right (e.g. `rahul123`) → that's the value.
3. Create a push token: **Account Settings → Personal access tokens → Generate**.
4. On your machine: `docker login` → enter username + the token.

**Apply the username everywhere at once:**
```bash
cd /path/to/developer-command-center
grep -rl YOUR_DOCKERHUB_USER k8s scripts Jenkinsfile \
  | xargs sed -i '' "s|YOUR_DOCKERHUB_USER|YOUR_ACTUAL_USERNAME|g"   # macOS
DOCKERHUB_USER=YOUR_ACTUAL_USERNAME ./scripts/build-and-push.sh
```

> Deploying to Minikube only? You can skip Docker Hub entirely by building images
> into Minikube's Docker daemon — see `scripts/build-and-push-local.sh`.

---

## 5. Jenkins credentials (optional)

Only if you run the Jenkins CI/CD setup. **Values in `jenkins/.env`:**

| Key | How to get it |
|---|---|
| `JENKINS_ADMIN_ID` / `JENKINS_ADMIN_PASSWORD` | You choose (defaults `admin`/`admin`). |
| `DOCKERHUB_USER` / `DOCKERHUB_TOKEN` | Section 4 (username + hub.docker.com access token). |
| `GITHUB_USER` / `GITHUB_TOKEN` | Your GitHub username + the PAT from Section 2. |
| `KUBECONFIG_B64` | Base64 of your kubeconfig after `minikube start` (below). |

**Getting `KUBECONFIG_B64` — step by step:**
1. `minikube start` (so `~/.kube/config` exists and points at the cluster).
2. Encode it to one line:
   ```bash
   base64 -i ~/.kube/config        # macOS
   base64 -w0 ~/.kube/config       # Linux
   ```
3. Paste the output as `KUBECONFIG_B64` in `jenkins/.env`.

Also edit the repo owner/repo in `jenkins/casc/jenkins.yaml`
(`PLACEHOLDER_GITHUB_OWNER` / `PLACEHOLDER_GITHUB_REPO`).

> Default `KUBECONFIG_B64` is `base64("PLACEHOLDER")` so Jenkins boots cleanly before
> you set a real one. See `jenkins/README.md` for run steps and caveats.

---

## Full placeholder checklist

- [ ] `.env` → `ANTHROPIC_API_KEY`
- [ ] `.env` → `ANTHROPIC_BASE_URL` (if given a custom endpoint)
- [ ] `.env` → `GITHUB_TOKEN`, `GITHUB_REPOS`, `GITHUB_POLL_ENABLED=true` (for live ingest)
- [ ] `.env` → DB / RabbitMQ passwords (optional locally)
- [ ] `k8s/secrets.yaml` → `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, DB passwords, `RABBITMQ_PASSWORD` (for K8s)
- [ ] `YOUR_DOCKERHUB_USER` replaced in `k8s/services/*.yaml`, `Jenkinsfile`, `scripts/build-and-push.sh`
- [ ] `jenkins/.env` → Docker Hub, GitHub, `KUBECONFIG_B64` (only if using Jenkins)
- [ ] `jenkins/casc/jenkins.yaml` → repo owner/name (only if using Jenkins)

**Secrets never to commit:** `.env`, `jenkins/.env`, and real values in
`k8s/secrets.yaml`. The first two are already in `.gitignore`.
