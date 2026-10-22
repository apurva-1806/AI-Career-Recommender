"""Runtime configuration, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _normalise_db_url(url: str) -> str:
    """Accept plain postgres/sqlite URLs and switch them to their async drivers."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    return url


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _normalise_db_url(
        os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'career.db'}")))
    # auto  -> sentence-transformers if it can be loaded, otherwise TF-IDF
    # sbert -> sentence-transformers only (startup fails if unavailable)
    # tfidf -> scikit-learn TF-IDF only
    embedding_backend: str = field(default_factory=lambda: os.getenv("EMBEDDING_BACKEND", "auto").lower())
    sbert_model: str = field(default_factory=lambda: os.getenv("SBERT_MODEL", "all-MiniLM-L6-v2"))
    top_k: int = field(default_factory=lambda: int(os.getenv("TOP_K", "5")))
    cors_origins: list[str] = field(default_factory=lambda: _split(
        os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")))
    careers_csv: Path = field(default_factory=lambda: Path(
        os.getenv("CAREERS_CSV", BASE_DIR / "data" / "careers.csv")))
    resources_json: Path = field(default_factory=lambda: Path(
        os.getenv("RESOURCES_JSON", BASE_DIR / "data" / "learning_resources.json")))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))))
    sql_echo: bool = field(default_factory=lambda: os.getenv("SQL_ECHO", "0") == "1")
    # Supervised ML classifier (ml_model.py). Trained automatically on first start.
    use_classifier: bool = field(default_factory=lambda: os.getenv("USE_CLASSIFIER", "1") == "1")
    model_path: Path = field(default_factory=lambda: Path(
        os.getenv("CAREER_MODEL_PATH", BASE_DIR / "models" / "career_classifier.joblib")))
    samples_per_career: int = field(default_factory=lambda: int(os.getenv("SAMPLES_PER_CAREER", "80")))
    # Accounts
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "30")))
    # Set COOKIE_SECURE=1 when the site is served over HTTPS so the session cookie is HTTPS-only.
    cookie_secure: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "0") == "1")
    cookie_samesite: str = field(default_factory=lambda: os.getenv("COOKIE_SAMESITE", "lax").lower())
    password_iterations: int = field(default_factory=lambda: int(os.getenv("PASSWORD_ITERATIONS", "600000")))


def get_settings() -> Settings:
    return Settings()
