"""SQLAlchemy models for ai-review-service (reviews-db)."""
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pr_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    pr_number: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    degraded: Mapped[int] = mapped_column(Integer, default=0)  # 1 if fallback/no-context
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_pattern: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    focus_areas: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(64), default="general")


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed a sensible default template if none exist.
    from sqlalchemy import select, func
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(PromptTemplate))
        if not total:
            session.add(PromptTemplate(
                repo_pattern="*",
                focus_areas="correctness, error handling, readability, test coverage",
                language="general",
            ))
            await session.commit()
