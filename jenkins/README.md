# Jenkins CI/CD (optional, reference setup)

A local Jenkins LTS that provisions the two pipeline credentials
(`dockerhub-credentials`, `kubeconfig`) **and** `github-token` automatically via
Configuration-as-Code. You only edit placeholders in `jenkins/.env` — no manual
credential clicking in the UI.

> You said image creation and cluster connection are done manually. This folder
> is a ready-to-use reference: it brings Jenkins up with everything wired to
> placeholders. Fill them in only if/when you want the pipeline to actually run.

## What gets created

| Credential ID | Type | Used by (in `Jenkinsfile`) | Placeholder source |
|---|---|---|---|
| `dockerhub-credentials` | username + password | Build & Push stage (`docker login`) | `DOCKERHUB_USER`, `DOCKERHUB_TOKEN` |
| `github-token` | username + password | Multibranch repo scanning | `GITHUB_USER`, `GITHUB_TOKEN` |
| `kubeconfig` | secret file | Deploy stage (`kubectl`) | `KUBECONFIG_B64` |

A multibranch pipeline job `developer-command-center` is also seeded (pointing at
`PLACEHOLDER_GITHUB_OWNER/PLACEHOLDER_GITHUB_REPO` — edit in `casc/jenkins.yaml`).

## Run it

```bash
cd jenkins
cp .env.example .env        # fill in placeholders (all optional for first boot)
docker compose -f docker-compose.jenkins.yml up --build -d
# open http://localhost:8081   (login: JENKINS_ADMIN_ID / JENKINS_ADMIN_PASSWORD)
```

## Filling the placeholders (step by step)

1. **Docker Hub** → `DOCKERHUB_USER` = your hub.docker.com username;
   `DOCKERHUB_TOKEN` = Account Settings → Personal access tokens → Generate.
2. **GitHub** → `GITHUB_USER` = your username; `GITHUB_TOKEN` = Developer settings →
   fine-grained PAT (repo read). Also set the owner/repo in `casc/jenkins.yaml`.
3. **kubeconfig** → after `minikube start`:
   ```bash
   base64 -i ~/.kube/config        # macOS  (Linux: base64 -w0 ~/.kube/config)
   ```
   Paste the one-line output as `KUBECONFIG_B64` in `.env`.
4. Recreate Jenkins to apply: `docker compose -f docker-compose.jenkins.yml up -d --build`

## Notes / caveats

- Minikube's kubeconfig points at `127.0.0.1` and local cert files; a containerized
  Jenkins can't reach that as-is. For a real run, either run the `kubectl` stage on
  the host, use `minikube` with a routable API server, or run Jenkins on the host
  (`brew install jenkins-lts`) pointing at `casc/jenkins.yaml`.
- The app gateway uses host port **8080**; Jenkins is deliberately on **8081**.
- Changing `.env` requires recreating the container (JCasC resolves vars at boot).
