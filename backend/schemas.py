"""Request and response schemas for the API."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EducationLevel = Literal["high_school", "associate", "bachelor", "master", "doctorate"]

MAX_ITEMS = 60
MAX_ITEM_LENGTH = 60
MAX_BIO_LENGTH = 20_000


def _clean_list(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for value in values or []:
        text = " ".join(str(value).split())[:MAX_ITEM_LENGTH].strip(" ,;")
        if text:
            seen.setdefault(text.lower(), text)
    return list(seen.values())[:MAX_ITEMS]


class ProfileRequest(BaseModel):
    technical_skills: list[str] = Field(default_factory=list, examples=[["Python", "SQL", "React"]])
    soft_skills: list[str] = Field(default_factory=list, examples=[["Leadership", "Problem-solving"]])
    interests: list[str] = Field(default_factory=list, examples=[["AI research", "Creative writing"]])
    education_level: EducationLevel = "bachelor"
    years_experience: float = Field(default=0, ge=0, le=60)
    bio: str = Field(default="", max_length=MAX_BIO_LENGTH,
                     description="Optional resume text or short professional bio.")
    save_profile: bool = Field(default=True, description="Store the profile and its results in the database.")

    @field_validator("technical_skills", "soft_skills", "interests", mode="before")
    @classmethod
    def _normalise_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace(";", ",").split(",")
        return _clean_list(list(value))

    @field_validator("bio", mode="before")
    @classmethod
    def _strip_bio(cls, value):
        return (value or "").strip()

    @model_validator(mode="after")
    def _require_some_signal(self):
        if not (self.technical_skills or self.soft_skills or self.interests or len(self.bio) >= 30):
            raise ValueError("Add at least one skill or interest, or a bio of 30 characters or more.")
        return self


class Resource(BaseModel):
    title: str
    provider: str
    url: str
    type: str


class LearningStep(BaseModel):
    skill: str
    priority: Literal["core", "bonus"]
    resources: list[Resource]


class Salary(BaseModel):
    min: int
    max: int
    currency: str


class Growth(BaseModel):
    pct: float
    outlook: str
    note: str


class CareerSummary(BaseModel):
    id: str
    title: str
    industry: str
    description: str
    education_level: str
    education_label: str
    min_experience_years: int
    salary: Salary
    growth: Growth
    certifications: list[str]


class ScoreBreakdown(BaseModel):
    semantic_fit: float
    skill_fit: float
    readiness: float
    model_fit: float | None = Field(default=None, description="Classifier probability relative to its top pick.")
    weights: dict[str, float]


class RecommendationOut(BaseModel):
    rank: int
    career: CareerSummary
    match_score: float = Field(description="Overall match, 0-100.")
    confidence: str
    semantic_similarity: float = Field(description="Raw cosine similarity between profile and career vectors.")
    skill_coverage: float = Field(description="Share of required skills already covered, 0-1.")
    score_breakdown: ScoreBreakdown
    model_probability: float | None = Field(default=None, description="Classifier's predicted probability, 0-1.")
    why: str
    matched_skills: list[str]
    missing_skills: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    matched_traits: list[str]
    readiness_notes: list[str]
    learning_plan: list[LearningStep]


class ClassifierInfo(BaseModel):
    name: str
    accuracy: float
    top3_accuracy: float
    macro_f1: float
    log_loss: float
    training_samples: int
    trained_at: str


class EngineInfo(BaseModel):
    backend: str
    model: str
    careers_indexed: int
    classifier: ClassifierInfo | None = None


class RecommendResponse(BaseModel):
    profile_id: str | None
    generated_at: datetime
    engine: EngineInfo
    detected_skills: list[str]
    recommendations: list[RecommendationOut]


class CareerOut(BaseModel):
    id: str
    title: str
    industry: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    traits: list[str]
    education_level: str
    min_experience_years: int
    salary_min: int
    salary_max: int
    currency: str
    growth_pct: float
    outlook_note: str
    certifications: list[str]


class SkillOut(BaseModel):
    name: str
    category: str
    career_count: int


class MetaResponse(BaseModel):
    engine: EngineInfo
    education_levels: list[dict]
    industries: list[str]
    technical_skills: list[SkillOut]
    soft_skills: list[SkillOut]
    salary_note: str


class ResumeParseResponse(BaseModel):
    filename: str
    characters: int
    truncated: bool
    text: str
    detected_technical_skills: list[str]
    detected_soft_skills: list[str]


class StoredRecommendation(BaseModel):
    rank: int
    career_id: str
    career_title: str
    match_score: float
    semantic_similarity: float
    skill_coverage: float
    matched_skills: list[str]
    missing_skills: list[str]


class StoredProfile(BaseModel):
    id: str
    created_at: datetime
    technical_skills: list[str]
    soft_skills: list[str]
    interests: list[str]
    education_level: str
    years_experience: float
    bio: str
    recommendations: list[StoredRecommendation]


# --------------------------------------------------------------------------- accounts
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


def _clean_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not _EMAIL.match(email):
        raise ValueError("Enter a valid email address.")
    return email


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value):
        return " ".join(str(value or "").split())

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value):
        return _clean_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value):
        return _clean_email(value)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime


class SavedProfile(BaseModel):
    technical_skills: list[str]
    soft_skills: list[str]
    interests: list[str]
    education_level: str
    years_experience: float
    bio: str


class RunTopMatch(BaseModel):
    title: str
    match_score: float


class RunSummary(BaseModel):
    """One saved run, as listed on the history page."""
    id: str
    created_at: datetime
    skills: list[str]
    top_matches: list[RunTopMatch]


class RunDetail(BaseModel):
    """A saved run with everything needed to reopen the form and the dashboard."""
    id: str
    created_at: datetime
    profile: SavedProfile
    results: RecommendResponse
