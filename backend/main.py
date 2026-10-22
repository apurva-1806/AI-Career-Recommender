"""FastAPI application: routes for accounts, profiles, resume parsing, careers and recommendations.

Run locally with:  uvicorn main:app --reload --port 8000
Interactive docs:  http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import auth
import database as db
from config import get_settings
from ml_model import load_or_train
from model import EDUCATION_LEVELS, CareerRecommender, ProfileInput, build_backend, load_resources
from resume import ResumeError, extract_text
from schemas import (CareerOut, LoginRequest, MetaResponse, ProfileRequest, RecommendResponse,
                     RegisterRequest, ResumeParseResponse, RunDetail, RunSummary, StoredProfile, UserOut)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("career.api")

SALARY_NOTE = ("Salary bands and growth figures come from the bundled demo dataset. Salaries are illustrative "
               "India-market estimates in rupees per year, not live labour-market data.")
MAX_RESUME_CHARS = 20_000


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables, seed the dataset on first run and build the recommender once."""
    settings = get_settings()
    db.init_engine(settings)
    await db.create_tables()
    async with db.get_sessionmaker()() as session:
        seeded = await db.seed_database(session, settings.careers_csv)
        if seeded:
            logger.info("Seeded %d careers from %s", seeded, settings.careers_csv)
        careers = [c.to_dict() for c in (await session.execute(select(db.Career).order_by(db.Career.title))).scalars()]

    backend = await run_in_threadpool(build_backend, settings.embedding_backend, settings.sbert_model)
    classifier = None
    if settings.use_classifier:
        classifier = await run_in_threadpool(
            load_or_train, careers, settings.model_path, settings.samples_per_career)
    app.state.recommender = await run_in_threadpool(
        CareerRecommender, careers, backend, load_resources(settings.resources_json), classifier)
    app.state.settings = settings
    logger.info("Recommender ready: %s", app.state.recommender.engine_info)
    yield
    await db.dispose_engine()


app = FastAPI(title="AI Career Recommendation API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,          # the session cookie must be sent with API calls
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def get_recommender(request: Request) -> CareerRecommender:
    return request.app.state.recommender


# --------------------------------------------------------------------------- routes
@app.get("/api/health")
async def health(recommender: CareerRecommender = Depends(get_recommender)) -> dict:
    return {"status": "ok", "engine": recommender.engine_info}


@app.get("/api/model")
async def model_report(recommender: CareerRecommender = Depends(get_recommender)) -> dict:
    """How the ML classifier was trained and how each candidate algorithm scored on held-out data."""
    if recommender.classifier is None:
        raise HTTPException(status_code=404, detail="The ML classifier is turned off (USE_CLASSIFIER=0).")
    return recommender.classifier.report


@app.get("/api/meta", response_model=MetaResponse)
async def meta(session: AsyncSession = Depends(db.get_session),
               recommender: CareerRecommender = Depends(get_recommender)) -> dict:
    """Everything the profile form needs: skill suggestions, education levels, industries."""
    skills = (await session.execute(
        select(db.Skill).order_by(db.Skill.career_count.desc(), db.Skill.display_name))).scalars().all()
    industries = (await session.execute(select(db.Career.industry).distinct().order_by(db.Career.industry))).scalars().all()

    def as_out(skill: db.Skill) -> dict:
        return {"name": skill.display_name, "category": skill.category, "career_count": skill.career_count}

    return {
        "engine": recommender.engine_info,
        "education_levels": [{"value": key, "label": value["label"]} for key, value in EDUCATION_LEVELS.items()],
        "industries": list(industries),
        "technical_skills": [as_out(s) for s in skills if s.category == "technical"],
        "soft_skills": [as_out(s) for s in skills if s.category == "soft"],
        "salary_note": SALARY_NOTE,
    }


@app.get("/api/careers", response_model=list[CareerOut])
async def list_careers(industry: str | None = Query(default=None),
                       q: str | None = Query(default=None, description="Search in title and description."),
                       session: AsyncSession = Depends(db.get_session)) -> list[db.Career]:
    statement = select(db.Career).order_by(db.Career.title)
    if industry:
        statement = statement.where(db.Career.industry == industry)
    if q:
        like = f"%{q.strip()}%"
        statement = statement.where(db.Career.title.ilike(like) | db.Career.description.ilike(like))
    return list((await session.execute(statement)).scalars())


@app.get("/api/careers/{career_id}", response_model=CareerOut)
async def get_career(career_id: str, session: AsyncSession = Depends(db.get_session)) -> db.Career:
    career = await session.get(db.Career, career_id)
    if career is None:
        raise HTTPException(status_code=404, detail="Career not found.")
    return career


@app.post("/api/resume/parse", response_model=ResumeParseResponse)
async def parse_resume(file: UploadFile = File(...),
                       recommender: CareerRecommender = Depends(get_recommender)) -> dict:
    """Extract text from an uploaded resume and list the known skills found in it."""
    limit = app.state.settings.max_upload_bytes
    payload = await file.read(limit + 1)
    if len(payload) > limit:
        raise HTTPException(status_code=413, detail=f"File is larger than {limit // (1024 * 1024)} MB.")
    try:
        text = await run_in_threadpool(extract_text, file.filename or "", payload)
    except ResumeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    truncated = len(text) > MAX_RESUME_CHARS
    text = text[:MAX_RESUME_CHARS]
    taxonomy = recommender.taxonomy
    found = taxonomy.extract(text)
    return {
        "filename": file.filename or "resume",
        "characters": len(text),
        "truncated": truncated,
        "text": text,
        "detected_technical_skills": [taxonomy.name(s) for s in found if taxonomy.category[s] == "technical"],
        "detected_soft_skills": [taxonomy.name(s) for s in found if taxonomy.category[s] == "soft"],
    }


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(payload: ProfileRequest,
                    top_k: int | None = Query(default=None, ge=1, le=20),
                    session: AsyncSession = Depends(db.get_session),
                    user: db.User | None = Depends(auth.get_optional_user),
                    recommender: CareerRecommender = Depends(get_recommender)) -> dict:
    """Rank careers for a profile and return gap analysis, learning plan and market data.

    The run is stored unless save_profile is false: in the signed-in user's account when
    there is one, otherwise without an owner. The landing page's live example sends
    save_profile=false so it never lands in anyone's history.
    """
    profile = ProfileInput(
        technical_skills=payload.technical_skills, soft_skills=payload.soft_skills,
        interests=payload.interests, education_level=payload.education_level,
        years_experience=payload.years_experience, bio=payload.bio)
    k = top_k or app.state.settings.top_k
    result = await run_in_threadpool(recommender.recommend, profile, k)   # CPU-bound: keep the loop free

    profile_id = None
    if payload.save_profile:
        record = db.UserProfile(
            user_id=user.id if user else None, result=result,
            technical_skills=payload.technical_skills, soft_skills=payload.soft_skills,
            interests=payload.interests, education_level=payload.education_level,
            years_experience=payload.years_experience, bio=payload.bio)
        record.recommendations = [
            db.Recommendation(
                career_id=item["career"]["id"], rank=item["rank"], match_score=item["match_score"],
                semantic_similarity=item["semantic_similarity"], skill_coverage=item["skill_coverage"],
                matched_skills=item["matched_skills"], missing_skills=item["missing_skills"],
                engine=result["engine"]["backend"])
            for item in result["recommendations"]
        ]
        session.add(record)
        await session.commit()
        profile_id = record.id

    return {"profile_id": profile_id, "generated_at": datetime.now(timezone.utc), **result}


@app.get("/api/profiles/{profile_id}", response_model=StoredProfile)
async def get_profile(profile_id: str, session: AsyncSession = Depends(db.get_session),
                      user: db.User | None = Depends(auth.get_optional_user)) -> dict:
    """Return a stored profile with its recommendations. Account-owned profiles are owner-only."""
    statement = (select(db.UserProfile).where(db.UserProfile.id == profile_id)
                 .options(selectinload(db.UserProfile.recommendations).selectinload(db.Recommendation.career)))
    record = (await session.execute(statement)).scalar_one_or_none()
    if record is None or (record.user_id and (user is None or user.id != record.user_id)):
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {
        "id": record.id, "created_at": auth.as_utc(record.created_at),
        "technical_skills": record.technical_skills, "soft_skills": record.soft_skills,
        "interests": record.interests, "education_level": record.education_level,
        "years_experience": record.years_experience, "bio": record.bio,
        "recommendations": [
            {"rank": r.rank, "career_id": r.career_id, "career_title": r.career.title,
             "match_score": r.match_score, "semantic_similarity": r.semantic_similarity,
             "skill_coverage": r.skill_coverage, "matched_skills": r.matched_skills,
             "missing_skills": r.missing_skills}
            for r in record.recommendations
        ],
    }


# --------------------------------------------------------------------------- accounts
def _user_out(user: db.User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "created_at": auth.as_utc(user.created_at)}


@app.post("/api/auth/register", response_model=UserOut, status_code=201)
async def register(payload: RegisterRequest, response: Response,
                   session: AsyncSession = Depends(db.get_session)) -> dict:
    """Create an account and sign in."""
    password_hash = await run_in_threadpool(auth.hash_password, payload.password)
    user = db.User(email=payload.email, name=payload.name, password_hash=password_hash)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    await auth.start_session(session, user, response)
    return _user_out(user)


@app.post("/api/auth/login", response_model=UserOut)
async def login(payload: LoginRequest, response: Response,
                session: AsyncSession = Depends(db.get_session)) -> dict:
    user = (await session.execute(select(db.User).where(db.User.email == payload.email))).scalar_one_or_none()
    if user is None:
        await run_in_threadpool(auth.burn_time, payload.password)
        valid = False
    else:
        valid = await run_in_threadpool(auth.verify_password, payload.password, user.password_hash)
    if not valid:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    await auth.start_session(session, user, response)
    return _user_out(user)


@app.post("/api/auth/logout", status_code=204)
async def logout(request: Request, response: Response, session: AsyncSession = Depends(db.get_session)) -> None:
    await auth.end_session(session, request, response)


@app.get("/api/auth/me", response_model=UserOut)
async def me(user: db.User = Depends(auth.get_current_user)) -> dict:
    return _user_out(user)


@app.delete("/api/auth/me", status_code=204)
async def delete_account(response: Response, user: db.User = Depends(auth.get_current_user),
                         session: AsyncSession = Depends(db.get_session)) -> None:
    """Delete the account with every saved profile, result and session."""
    await session.delete(await session.get(db.User, user.id))
    await session.commit()
    auth.clear_cookie(response)


# --------------------------------------------------------------------------- saved runs
def _run_detail(record: db.UserProfile) -> dict:
    created = auth.as_utc(record.created_at)
    return {
        "id": record.id, "created_at": created,
        "profile": {"technical_skills": record.technical_skills, "soft_skills": record.soft_skills,
                    "interests": record.interests, "education_level": record.education_level,
                    "years_experience": record.years_experience, "bio": record.bio},
        "results": {"profile_id": record.id, "generated_at": created, **(record.result or {})},
    }


def _owned_runs(user: db.User):
    return (select(db.UserProfile)
            .where(db.UserProfile.user_id == user.id, db.UserProfile.result.is_not(None))
            .order_by(db.UserProfile.created_at.desc(), db.UserProfile.id))


@app.get("/api/me/profile", response_model=RunDetail | None)
async def my_latest_run(user: db.User = Depends(auth.get_current_user),
                        session: AsyncSession = Depends(db.get_session)) -> dict | None:
    """The newest saved profile and its recommendations, or null if nothing is saved yet."""
    record = (await session.execute(_owned_runs(user).limit(1))).scalar_one_or_none()
    return _run_detail(record) if record else None


@app.get("/api/me/history", response_model=list[RunSummary])
async def my_history(limit: int = Query(default=50, ge=1, le=200),
                     user: db.User = Depends(auth.get_current_user),
                     session: AsyncSession = Depends(db.get_session)) -> list[dict]:
    """Saved runs, newest first."""
    records = (await session.execute(_owned_runs(user).limit(limit))).scalars().all()
    return [
        {"id": r.id, "created_at": auth.as_utc(r.created_at), "skills": r.technical_skills[:8],
         "top_matches": [{"title": item["career"]["title"], "match_score": item["match_score"]}
                         for item in (r.result or {}).get("recommendations", [])[:3]]}
        for r in records
    ]


async def _owned_run(run_id: str, user: db.User, session: AsyncSession) -> db.UserProfile:
    record = await session.get(db.UserProfile, run_id)
    if record is None or record.user_id != user.id or record.result is None:
        raise HTTPException(status_code=404, detail="Saved result not found.")
    return record


@app.get("/api/me/history/{run_id}", response_model=RunDetail)
async def my_run(run_id: str, user: db.User = Depends(auth.get_current_user),
                 session: AsyncSession = Depends(db.get_session)) -> dict:
    return _run_detail(await _owned_run(run_id, user, session))


@app.delete("/api/me/history/{run_id}", status_code=204)
async def delete_run(run_id: str, user: db.User = Depends(auth.get_current_user),
                     session: AsyncSession = Depends(db.get_session)) -> None:
    await session.delete(await _owned_run(run_id, user, session))
    await session.commit()
