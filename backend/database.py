"""Database models, async session setup and dataset seeding.

SQLite (via aiosqlite) is the default for local development. Point DATABASE_URL at
PostgreSQL (postgresql://user:pass@host/db) to use asyncpg instead; no code changes needed.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import pandas as pd
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from config import Settings, get_settings
from model import SKILL_ALIASES, normalize_skill


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Career(Base):
    """One career path from the dataset."""
    __tablename__ = "careers"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # slug, e.g. "data-scientist"
    title: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    education_level: Mapped[str] = mapped_column(String(20))
    min_experience_years: Mapped[int] = mapped_column(Integer, default=0)
    salary_min: Mapped[int] = mapped_column(Integer)
    salary_max: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    growth_pct: Mapped[float] = mapped_column(Float)
    outlook_note: Mapped[str] = mapped_column(String(255), default="")
    certifications: Mapped[list[str]] = mapped_column(JSON, default=list)

    def to_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Skill(Base):
    """Skill taxonomy entry, derived from the career dataset plus known aliases."""
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)        # canonical, lower-case
    display_name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20), index=True)                # "technical" | "soft"
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    career_count: Mapped[int] = mapped_column(Integer, default=0)                # how many careers use it


class User(Base):
    """A registered account. Passwords are stored only as salted PBKDF2 hashes."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profiles: Mapped[list["UserProfile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="UserProfile.created_at.desc()")
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    """A signed-in browser. Only a SHA-256 hash of the cookie token is stored."""
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class UserProfile(Base):
    """One submitted profile and the recommendations generated for it (a "run").

    Runs made while signed in carry user_id; the newest one is the account's current profile.
    """
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Full recommendation payload as returned to the browser, so past results reopen exactly.
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    technical_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    soft_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    interests: Mapped[list[str]] = mapped_column(JSON, default=list)
    education_level: Mapped[str] = mapped_column(String(20))
    years_experience: Mapped[float] = mapped_column(Float, default=0)
    bio: Mapped[str] = mapped_column(Text, default="")

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="Recommendation.rank")
    user: Mapped[User | None] = relationship(back_populates="profiles")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    career_id: Mapped[str] = mapped_column(ForeignKey("careers.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    match_score: Mapped[float] = mapped_column(Float)
    semantic_similarity: Mapped[float] = mapped_column(Float)
    skill_coverage: Mapped[float] = mapped_column(Float)
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    engine: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped[UserProfile] = relationship(back_populates="recommendations")
    career: Mapped[Career] = relationship()


# --------------------------------------------------------------------------- engine / sessions
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create (or recreate) the global engine. Called once at application startup."""
    global _engine, _sessionmaker
    settings = settings or get_settings()
    _engine = create_async_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        init_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one session per request."""
    async with get_sessionmaker()() as session:
        yield session


async def create_tables(drop_first: bool = False) -> None:
    if _engine is None:
        init_engine()
    assert _engine is not None
    async with _engine.begin() as conn:
        if drop_first:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(connection) -> None:
    """Upgrade databases created before accounts existed (create_all never alters tables)."""
    existing = {column["name"] for column in inspect(connection).get_columns("user_profiles")}
    if "user_id" not in existing:
        connection.execute(text("ALTER TABLE user_profiles ADD COLUMN user_id VARCHAR(36) REFERENCES users(id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_user_profiles_user_id ON user_profiles (user_id)"))
    if "result" not in existing:
        connection.execute(text("ALTER TABLE user_profiles ADD COLUMN result JSON"))


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None


# --------------------------------------------------------------------------- seeding
def _split_list(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def load_careers_csv(path: Path) -> list[dict]:
    """Read and validate the careers CSV into a list of row dictionaries."""
    frame = pd.read_csv(path, keep_default_na=False, dtype=str)
    required = {"id", "title", "industry", "required_skills", "description", "education_level",
                "min_experience_years", "salary_min", "salary_max", "growth_pct"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    if frame["id"].duplicated().any():
        raise ValueError(f"{path} contains duplicate career ids")

    rows: list[dict] = []
    for record in frame.to_dict(orient="records"):
        rows.append({
            "id": record["id"].strip(),
            "title": record["title"].strip(),
            "industry": record["industry"].strip(),
            "description": record["description"].strip(),
            "required_skills": _split_list(record["required_skills"]),
            "preferred_skills": _split_list(record.get("preferred_skills")),
            "traits": _split_list(record.get("traits")),
            "education_level": record["education_level"].strip(),
            "min_experience_years": int(record["min_experience_years"]),
            "salary_min": int(record["salary_min"]),
            "salary_max": int(record["salary_max"]),
            "currency": (record.get("currency") or "INR").strip(),
            "growth_pct": float(record["growth_pct"]),
            "outlook_note": (record.get("outlook_note") or "").strip(),
            "certifications": _split_list(record.get("certifications")),
        })
    return rows


def build_taxonomy(careers: list[dict]) -> list[dict]:
    """Derive the skill taxonomy (canonical name, category, aliases, usage count) from careers."""
    display: dict[str, str] = {}
    category: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for career in careers:
        for column, kind in (("required_skills", "technical"), ("preferred_skills", "technical"), ("traits", "soft")):
            for raw in career[column]:
                key = normalize_skill(raw)
                display.setdefault(key, raw)
                category.setdefault(key, kind)
                counts[key] += 1

    aliases: dict[str, list[str]] = {}
    for alias, target in SKILL_ALIASES.items():
        aliases.setdefault(target, []).append(alias)

    return [
        {"name": key, "display_name": display[key], "category": category[key],
         "aliases": sorted(aliases.get(key, [])), "career_count": counts[key]}
        for key in sorted(display)
    ]


async def seed_database(session: AsyncSession, csv_path: Path, *, force: bool = False) -> int:
    """Load careers and the skill taxonomy if the tables are empty (or always, with force)."""
    existing = (await session.execute(select(func.count()).select_from(Career))).scalar_one()
    if existing and not force:
        return 0

    careers = load_careers_csv(csv_path)
    for row in careers:
        await session.merge(Career(**row))

    current = {s.name: s for s in (await session.execute(select(Skill))).scalars()}
    for entry in build_taxonomy(careers):
        if entry["name"] in current:
            for key, value in entry.items():
                setattr(current[entry["name"]], key, value)
        else:
            session.add(Skill(**entry))
    await session.commit()
    return len(careers)
