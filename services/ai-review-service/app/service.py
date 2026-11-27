"""Review orchestration: pick template -> fetch RAG context -> Claude -> store."""
import asyncio
import logging
from fnmatch import fnmatch

from sqlalchemy import select

from .models import PromptTemplate, Review, SessionLocal
from .github_client import fetch_pr_diff
from .grpc_rag_client import get_context  # Lab 3B: fetch project context over gRPC (was rag_client REST)
from .reviewer import generate_review

log = logging.getLogger("ai-review-service.service")


async def _select_template(repo: str) -> dict:
    async with SessionLocal() as session:
        rows = (await session.execute(select(PromptTemplate))).scalars().all()
    matches = [t for t in rows if fnmatch(repo, t.repo_pattern)]
    if not matches:
        return {"focus_areas": "correctness, readability", "language": "general"}
    # Most specific wins: a non-"*" pattern beats "*", then a longer pattern beats
    # a shorter one (e.g. "acme/api" beats "acme/*" beats "*").
    best = max(matches, key=lambda t: (t.repo_pattern != "*", len(t.repo_pattern)))
    return {"focus_areas": best.focus_areas, "language": best.language}


async def run_review(repo: str, pr: dict) -> dict:
    template = await _select_template(repo)
    # Run the blocking calls (gRPC context fetch, diff fetch, Claude SDK) OFF the
    # event loop so the consumer can process multiple prefetched messages concurrently.
    context, ctx_degraded = await asyncio.to_thread(get_context, repo)
    diff = await asyncio.to_thread(fetch_pr_diff, repo, int(pr.get("number", 0)))
    summary, ai_degraded = await asyncio.to_thread(generate_review, repo, pr, context, template, diff)
    degraded = 1 if (ctx_degraded or ai_degraded) else 0

    pr_id = pr.get("id") or f"pr-{repo}-{pr.get('number')}"
    async with SessionLocal() as session:
        # Idempotent: one review per pr_id. On redelivery (e.g. RabbitMQ requeue)
        # update the existing row in place instead of inserting a duplicate.
        existing = (await session.execute(
            select(Review).where(Review.pr_id == pr_id)
        )).scalars().first()
        if existing:
            existing.repo = repo
            existing.pr_number = int(pr.get("number", 0))
            existing.summary = summary
            existing.degraded = degraded
            review = existing
        else:
            review = Review(
                pr_id=pr_id, repo=repo, pr_number=int(pr.get("number", 0)),
                summary=summary, degraded=degraded,
            )
            session.add(review)
        await session.commit()
        await session.refresh(review)

    return {"id": review.id, "pr_id": pr_id, "repo": repo,
            "summary": summary, "degraded": bool(degraded)}


async def get_review(pr_id: str) -> dict | None:
    async with SessionLocal() as session:
        row = await session.execute(
            select(Review).where(Review.pr_id == pr_id).order_by(Review.id.desc())
        )
        r = row.scalars().first()
        if not r:
            return None
        return {"id": r.id, "pr_id": r.pr_id, "repo": r.repo, "pr_number": r.pr_number,
                "summary": r.summary, "degraded": bool(r.degraded),
                "created_at": r.created_at.isoformat()}


async def recent_reviews(limit: int = 10) -> list[dict]:
    async with SessionLocal() as session:
        rows = await session.execute(select(Review).order_by(Review.id.desc()).limit(limit))
        return [{"id": r.id, "pr_id": r.pr_id, "repo": r.repo, "summary": r.summary,
                 "degraded": bool(r.degraded)} for r in rows.scalars().all()]


async def upsert_template(repo_pattern: str, focus_areas: str, language: str) -> dict:
    async with SessionLocal() as session:
        row = await session.execute(
            select(PromptTemplate).where(PromptTemplate.repo_pattern == repo_pattern)
        )
        t = row.scalars().first()
        if t:
            t.focus_areas, t.language = focus_areas, language
        else:
            t = PromptTemplate(repo_pattern=repo_pattern, focus_areas=focus_areas, language=language)
            session.add(t)
        await session.commit()
    return {"repo_pattern": repo_pattern, "focus_areas": focus_areas, "language": language}


async def list_templates() -> list[dict]:
    async with SessionLocal() as session:
        rows = await session.execute(select(PromptTemplate))
        return [{"repo_pattern": t.repo_pattern, "focus_areas": t.focus_areas,
                 "language": t.language} for t in rows.scalars().all()]


async def delete_template(repo_pattern: str) -> dict:
    """Delete a prompt template by its exact repo_pattern (CRUD: Delete)."""
    async with SessionLocal() as session:
        t = (await session.execute(
            select(PromptTemplate).where(PromptTemplate.repo_pattern == repo_pattern)
        )).scalars().first()
        if not t:
            return {"deleted": 0, "repo_pattern": repo_pattern}
        await session.delete(t)
        await session.commit()
    return {"deleted": 1, "repo_pattern": repo_pattern}
