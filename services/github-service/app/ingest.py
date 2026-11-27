"""Persist GitHub entities to github-db and publish events to RabbitMQ.

Shared by the poller, the /webhook handler, and the /simulate demo endpoint,
so every ingestion path produces identical downstream events.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .github_client import client
from .models import Commit, Issue, PullRequest, Repo, SessionLocal
from .publisher import publisher

log = logging.getLogger("github-service.ingest")


async def _ensure_repo(session, full_name: str) -> None:
    stmt = pg_insert(Repo).values(full_name=full_name).on_conflict_do_nothing(
        index_elements=["full_name"]
    )
    await session.execute(stmt)


async def record_pull_request(repo: str, pr: dict) -> dict:
    """Upsert a PR row and publish a pr.opened / pr.closed event."""
    number = int(pr["number"])
    state = pr.get("state", "open")
    merged = bool(pr.get("merged")) or pr.get("merged_at") is not None or state == "merged"
    head_branch = (pr.get("head") or {}).get("ref") or pr.get("head_branch") or ""
    payload = {
        "type": "pull_request",
        "repo": repo,
        "number": number,
        "title": pr.get("title", ""),
        "state": state,
        "author": (pr.get("user") or {}).get("login", pr.get("author", "")),
        "body": pr.get("body") or "",
        "merged": merged,
        "head_branch": head_branch,
        "updated_at": pr.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }
    async with SessionLocal() as session:
        await _ensure_repo(session, repo)
        stmt = pg_insert(PullRequest).values(
            repo=repo, number=number, title=payload["title"], state=state,
            author=payload["author"], body=payload["body"],
            merged=merged, head_branch=head_branch,
        ).on_conflict_do_update(
            index_elements=["repo", "number"],
            set_={"title": payload["title"], "state": state, "body": payload["body"],
                  "merged": merged, "head_branch": head_branch},
        )
        await session.execute(stmt)
        await session.commit()

    routing_key = "pr.closed" if state in ("closed", "merged") else "pr.opened"
    await publisher.publish(routing_key, {"id": f"pr-{repo}-{number}", **payload})
    # A high-signal alert on newly opened PRs → DIRECT notifications exchange.
    if routing_key == "pr.opened":
        await publisher.publish_alert({
            "id": f"alert-pr-{repo}-{number}", "type": "alert", "alert": "pr.opened",
            "repo": repo, "number": number, "title": payload["title"],
        })
    return payload


async def record_issue(repo: str, issue: dict) -> dict:
    number = int(issue["number"])
    payload = {
        "type": "issue",
        "repo": repo,
        "number": number,
        "title": issue.get("title", ""),
        "state": issue.get("state", "open"),
        "body": issue.get("body") or "",
        "updated_at": issue.get("updated_at") or datetime.now(timezone.utc).isoformat(),
    }
    async with SessionLocal() as session:
        await _ensure_repo(session, repo)
        stmt = pg_insert(Issue).values(
            repo=repo, number=number, title=payload["title"],
            state=payload["state"], body=payload["body"],
        ).on_conflict_do_update(
            index_elements=["repo", "number"],
            set_={"title": payload["title"], "state": payload["state"], "body": payload["body"]},
        )
        await session.execute(stmt)
        await session.commit()
    await publisher.publish("issue.created", {"id": f"issue-{repo}-{number}", **payload})
    return payload


async def record_commit(repo: str, commit: dict) -> dict:
    sha = commit.get("sha", "")
    commit_obj = commit.get("commit", {})
    message = commit_obj.get("message") or commit.get("message", "")
    author = (commit_obj.get("author") or {}).get("name") or commit.get("author", "")
    payload = {
        "type": "commit",
        "repo": repo,
        "sha": sha,
        "message": message,
        "author": author,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    async with SessionLocal() as session:
        await _ensure_repo(session, repo)
        stmt = pg_insert(Commit).values(
            repo=repo, sha=sha, message=message, author=author,
        ).on_conflict_do_nothing(index_elements=["repo", "sha"])
        await session.execute(stmt)
        await session.commit()
    await publisher.publish("commit.pushed", {"id": f"commit-{repo}-{sha[:10]}", **payload})
    return payload


async def ingest_repo(repo: str) -> dict:
    """Live ingestion path — requires a real GITHUB_TOKEN (circuit-breaker wrapped)."""
    prs = await client.list_pull_requests(repo)
    for pr in prs:
        await record_pull_request(repo, pr)
    issues = await client.list_issues(repo)
    for issue in issues:
        if "pull_request" in issue:   # GitHub returns PRs in the issues list; skip
            continue
        await record_issue(repo, issue)
    commits = await client.list_commits(repo)
    for commit in commits:
        await record_commit(repo, commit)
    return {"repo": repo, "prs": len(prs), "commits": len(commits)}


async def list_repos() -> list[str]:
    async with SessionLocal() as session:
        rows = await session.execute(select(Repo.full_name))
        return [r[0] for r in rows.all()]


async def list_prs(repo: str) -> list[dict]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(PullRequest).where(PullRequest.repo == repo)
        )
        return [
            {"number": p.number, "title": p.title, "state": p.state,
             "author": p.author, "merged": p.merged, "head_branch": p.head_branch}
            for p in rows.scalars().all()
        ]


async def mark_pr_merged(repo: str, number: int) -> None:
    """Reflect a successful GitHub merge in the local store."""
    async with SessionLocal() as session:
        await session.execute(
            pg_insert(PullRequest).values(
                repo=repo, number=number, state="closed", merged=True,
            ).on_conflict_do_update(
                index_elements=["repo", "number"],
                set_={"state": "closed", "merged": True},
            )
        )
        await session.commit()


async def update_repo_pr(repo: str, number: int, fields: dict) -> dict:
    """Explicit local Update of a PR's title/state/body (A1 Update verb)."""
    allowed = {k: v for k, v in fields.items() if k in ("title", "state", "body")}
    async with SessionLocal() as session:
        row = await session.execute(
            select(PullRequest).where(
                PullRequest.repo == repo, PullRequest.number == number
            )
        )
        pr = row.scalar_one_or_none()
        if pr is None:
            return {"updated": 0, "repo": repo, "number": number}
        for k, v in allowed.items():
            setattr(pr, k, v)
        await session.commit()
    return {"updated": 1, "repo": repo, "number": number, "fields": allowed}


async def delete_pr(repo: str, number: int) -> dict:
    """Stop tracking one PR locally and announce it for downstream cleanup."""
    async with SessionLocal() as session:
        res = await session.execute(
            sa_delete(PullRequest).where(
                PullRequest.repo == repo, PullRequest.number == number
            )
        )
        await session.commit()
    deleted = res.rowcount or 0
    await publisher.publish("pr.untracked", {
        "id": f"untrack-pr-{repo}-{number}", "type": "pr.untracked",
        "repo": repo, "number": number, "deleted": deleted,
    })
    return {"repo": repo, "number": number, "deleted_pr": deleted}


async def delete_repo(full_name: str) -> dict:
    """Stop tracking a repo and all its activity locally; announce it."""
    async with SessionLocal() as session:
        prs = (await session.execute(
            sa_delete(PullRequest).where(PullRequest.repo == full_name))).rowcount or 0
        issues = (await session.execute(
            sa_delete(Issue).where(Issue.repo == full_name))).rowcount or 0
        commits = (await session.execute(
            sa_delete(Commit).where(Commit.repo == full_name))).rowcount or 0
        repos = (await session.execute(
            sa_delete(Repo).where(Repo.full_name == full_name))).rowcount or 0
        await session.commit()
    counts = {"deleted_repo": repos, "prs": prs, "issues": issues, "commits": commits}
    await publisher.publish("repo.untracked", {
        "id": f"untrack-repo-{full_name}", "type": "repo.untracked",
        "repo": full_name, **counts,
    })
    return counts
