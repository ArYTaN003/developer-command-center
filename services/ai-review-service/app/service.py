"""Review orchestration: pick template -> fetch RAG context -> Claude -> store."""
import logging
from fnmatch import fnmatch

from sqlalchemy import select

from .models import PromptTemplate, Review, SessionLocal
from .grpc_rag_client import get_context  # Lab 3B: fetch project context over gRPC (was rag_client REST)
from .reviewer import generate_review

log = logging.getLogger("ai-review-service.service")


async def _select_template(repo: str) -> dict:
    async with SessionLocal() as session:
        rows = (await session.execute(select(PromptTemplate))).scalars().all()
    best = None
    for t in rows:
        if fnmatch(repo, t.repo_pattern):
            # prefer the most specific (non-"*") pattern
            if best is None or t.repo_pattern != "*":
                best = t
    if best is None:
        return {"focus_areas": "correctness, readability", "language": "general"}
    return {"focus_areas": best.focus_areas, "language": best.language}


async def run_review(repo: str, pr: dict) -> dict:
    template = await _select_template(repo)
    context, ctx_degraded = get_context(repo)
    summary, ai_degraded = generate_review(repo, pr, context, template)
    degraded = 1 if (ctx_degraded or ai_degraded) else 0

    pr_id = pr.get("id") or f"pr-{repo}-{pr.get('number')}"
    async with SessionLocal() as session:
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
