"""End-to-end tests. Run from the backend folder:  pytest -q"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="career-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test.db"
os.environ["PASSWORD_ITERATIONS"] = "1000"   # keep hashing fast in tests
os.environ["CAREER_MODEL_PATH"] = f"{_TMP}/career_classifier.joblib"   # never touch the real model file
os.environ["SAMPLES_PER_CAREER"] = "40"
os.environ["EMBEDDING_BACKEND"] = "tfidf"   # fast and offline; no model download in tests

from fastapi.testclient import TestClient  # noqa: E402

import database as db  # noqa: E402
import main  # noqa: E402
from model import (CareerRecommender, ProfileInput, SkillTaxonomy, clean_text, normalize_skill,  # noqa: E402
                   tokenize)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def titles(response) -> list[str]:
    return [item["career"]["title"] for item in response.json()["recommendations"]]


# --------------------------------------------------------------------------- NLP helpers
def test_text_cleaning_and_tokenising():
    text = "Contact me at jane@example.com or https://jane.dev — I build APIs with Node.js, C++ & C#!"
    assert "example.com" not in clean_text(text) and "https" not in clean_text(text)
    tokens = tokenize(text)
    assert {"node.js", "c++", "c#", "apis"} <= set(tokens)
    assert "with" not in tokens


def test_skill_normalisation():
    assert normalize_skill("  JS ") == "javascript"
    assert normalize_skill("K8s") == "kubernetes"
    assert normalize_skill("Problem Solving") == "problem-solving"
    assert normalize_skill("Rust") == "rust"


def test_taxonomy_extraction_and_implied_skills():
    careers = db.load_careers_csv(BACKEND / "data" / "careers.csv")
    taxonomy = SkillTaxonomy(careers)
    found = taxonomy.extract("Built ETL pipelines in Python and Postgres; shipped dashboards in PowerBI. Go team!")
    assert {"python", "postgresql", "power bi", "etl"} <= set(found)
    assert "go" not in found                                  # ambiguous word, not extracted from prose
    assert {"sql", "data visualization"} <= taxonomy.expand(found)


def test_dataset_shape():
    careers = db.load_careers_csv(BACKEND / "data" / "careers.csv")
    assert len(careers) >= 50
    assert all(len(c["required_skills"]) >= 5 and c["salary_max"] > c["salary_min"] for c in careers)
    assert len({c["industry"] for c in careers}) >= 10


# --------------------------------------------------------------------------- API
def test_health_and_meta(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["engine"]["backend"] == "tfidf" and meta["engine"]["careers_indexed"] >= 50
    assert len(meta["technical_skills"]) > 100 and len(meta["soft_skills"]) > 20
    assert [level["value"] for level in meta["education_levels"]][0] == "high_school"


def test_careers_listing_and_lookup(client):
    everything = client.get("/api/careers").json()
    assert len(everything) >= 50
    finance = client.get("/api/careers", params={"industry": "Finance"}).json()
    assert finance and all(c["industry"] == "Finance" for c in finance)
    assert client.get("/api/careers/data-scientist").json()["title"] == "Data Scientist"
    assert client.get("/api/careers/nope").status_code == 404


def test_recommend_data_profile(client):
    response = client.post("/api/recommend", json={
        "technical_skills": ["Python", "SQL", "Machine Learning", "pandas", "Statistics", "sklearn"],
        "soft_skills": ["Problem solving", "Curiosity"], "interests": ["AI research"],
        "education_level": "master", "years_experience": 3,
        "bio": "Data scientist who builds predictive models and runs A/B tests for product teams."})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["recommendations"]) == 5
    assert titles(response)[0] in {"Data Scientist", "Machine Learning Engineer"}
    scores = [r["match_score"] for r in body["recommendations"]]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
    top = body["recommendations"][0]
    assert "Python" in top["matched_skills"] and top["why"]
    assert not set(top["matched_skills"]) & set(top["missing_skills"])
    assert all(step["resources"] for step in top["learning_plan"])
    assert "A/B Testing" in body["detected_skills"]


def test_recommend_frontend_and_writing_profiles(client):
    frontend = client.post("/api/recommend", json={
        "technical_skills": ["React", "JS", "TypeScript", "HTML", "CSS", "Figma"],
        "soft_skills": ["Creativity"], "education_level": "bachelor", "years_experience": 1})
    assert titles(frontend)[0] == "Frontend Developer"

    writer = client.post("/api/recommend", json={
        "soft_skills": ["Creative writing", "Storytelling", "Empathy"],
        "interests": ["Writing"], "technical_skills": ["Copywriting", "SEO", "Editing"],
        "education_level": "bachelor", "years_experience": 0})
    assert {"Copywriter", "Content Strategist"} & set(titles(writer)[:3])


def test_seniority_changes_readiness(client):
    base = {"technical_skills": ["AWS", "Azure", "System Design", "Networking", "Terraform", "Kubernetes"],
            "education_level": "bachelor", "save_profile": False}
    junior = client.post("/api/recommend", params={"top_k": 20}, json={**base, "years_experience": 0}).json()
    senior = client.post("/api/recommend", params={"top_k": 20}, json={**base, "years_experience": 8}).json()

    def architect(body):
        return next(r for r in body["recommendations"] if r["career"]["title"] == "Cloud Solutions Architect")

    assert architect(senior)["match_score"] > architect(junior)["match_score"]
    assert architect(junior)["readiness_notes"] and not architect(senior)["readiness_notes"]
    assert junior["profile_id"] is None


def test_profile_is_stored(client):
    created = client.post("/api/recommend", json={
        "technical_skills": ["Excel", "Accounting"], "education_level": "bachelor", "years_experience": 2}).json()
    stored = client.get(f"/api/profiles/{created['profile_id']}").json()
    assert stored["technical_skills"] == ["Excel", "Accounting"]
    assert [r["rank"] for r in stored["recommendations"]] == [1, 2, 3, 4, 5]
    assert client.get("/api/profiles/missing").status_code == 404


def test_validation_errors(client):
    assert client.post("/api/recommend", json={"education_level": "bachelor"}).status_code == 422
    assert client.post("/api/recommend", json={"technical_skills": ["Python"], "education_level": "phd"}).status_code == 422
    assert client.post("/api/recommend", json={"technical_skills": ["Python"], "years_experience": -1}).status_code == 422


def test_resume_parsing(client):
    resume = (b"Jane Doe\nSenior Analyst\nSkills: SQL, Tableau, Python, stakeholder management.\n"
              b"Led a team of four analysts; strong communication and leadership.")
    parsed = client.post("/api/resume/parse", files={"file": ("resume.txt", io.BytesIO(resume), "text/plain")})
    assert parsed.status_code == 200, parsed.text
    body = parsed.json()
    assert {"SQL", "Tableau", "Python", "Stakeholder Management"} <= set(body["detected_technical_skills"])
    assert "Leadership" in body["detected_soft_skills"]

    bad = client.post("/api/resume/parse", files={"file": ("resume.exe", io.BytesIO(b"x" * 50), "application/octet-stream")})
    assert bad.status_code == 422


def test_docx_resume(client):
    from docx import Document

    document = Document()
    document.add_paragraph("Frontend engineer with five years of React, TypeScript and accessibility work.")
    buffer = io.BytesIO()
    document.save(buffer)
    parsed = client.post("/api/resume/parse", files={"file": ("cv.docx", io.BytesIO(buffer.getvalue()),
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert parsed.status_code == 200, parsed.text
    assert {"React", "TypeScript", "Accessibility"} <= set(parsed.json()["detected_technical_skills"])


# --------------------------------------------------------------------------- accounts
PROFILE_A = {"technical_skills": ["Python", "SQL", "Tableau"], "soft_skills": ["Curiosity"],
             "education_level": "bachelor", "years_experience": 2}
PROFILE_B = {"technical_skills": ["React", "TypeScript", "CSS"], "education_level": "bachelor", "years_experience": 1}


def test_password_hashing():
    import auth

    stored = auth.hash_password("correct horse", iterations=1000)
    assert "correct horse" not in stored and stored.startswith("pbkdf2_sha256$1000$")
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong horse", stored)
    assert not auth.verify_password("x", "garbage")
    assert auth.hash_password("correct horse", iterations=1000) != stored      # fresh salt each time


def test_register_login_and_saved_runs():
    with TestClient(main.app) as asha, TestClient(main.app) as ravi:
        assert asha.get("/api/auth/me").status_code == 401
        assert asha.get("/api/me/profile").status_code == 401

        created = asha.post("/api/auth/register", json={"name": " Asha  Rao ", "email": "Asha@Example.com", "password": "s3cret-pass"})
        assert created.status_code == 201, created.text
        assert created.json()["email"] == "asha@example.com" and created.json()["name"] == "Asha Rao"
        assert "password" not in created.text
        cookie = created.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert asha.get("/api/auth/me").json()["name"] == "Asha Rao"
        assert asha.get("/api/me/profile").json() is None

        # validation and duplicates
        assert ravi.post("/api/auth/register", json={"name": "R", "email": "asha@example.com", "password": "another-pass"}).status_code == 409
        assert ravi.post("/api/auth/register", json={"name": "R", "email": "not-an-email", "password": "another-pass"}).status_code == 422
        assert ravi.post("/api/auth/register", json={"name": "R", "email": "ravi@example.com", "password": "short"}).status_code == 422
        assert ravi.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong-pass"}).status_code == 401
        assert ravi.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}).status_code == 401

        # a run sent with save_profile false (the landing page example) is never stored
        assert asha.post("/api/recommend", json={**PROFILE_A, "save_profile": False}).json()["profile_id"] is None
        assert asha.get("/api/me/history").json() == []

        # two saved runs, newest first
        first = asha.post("/api/recommend", json=PROFILE_A).json()
        second = asha.post("/api/recommend", json=PROFILE_B).json()
        assert first["profile_id"] and second["profile_id"]
        latest = asha.get("/api/me/profile").json()
        assert latest["id"] == second["profile_id"]
        assert latest["profile"]["technical_skills"] == ["React", "TypeScript", "CSS"]
        assert latest["results"]["recommendations"][0]["career"]["title"] == "Frontend Developer"
        assert latest["results"]["recommendations"][0]["learning_plan"] is not None
        assert latest["created_at"].endswith(("Z", "+00:00"))
        history = asha.get("/api/me/history").json()
        assert [run["id"] for run in history] == [second["profile_id"], first["profile_id"]]
        assert history[0]["top_matches"][0]["title"] == "Frontend Developer" and len(history[0]["top_matches"]) == 3
        assert asha.get(f"/api/me/history/{first['profile_id']}").json()["profile"]["technical_skills"] == PROFILE_A["technical_skills"]

        # another account cannot see or delete them
        assert ravi.post("/api/auth/register", json={"name": "Ravi", "email": "ravi@example.com", "password": "another-pass"}).status_code == 201
        assert ravi.get("/api/me/history").json() == []
        assert ravi.get(f"/api/me/history/{first['profile_id']}").status_code == 404
        assert ravi.delete(f"/api/me/history/{first['profile_id']}").status_code == 404
        assert ravi.get(f"/api/profiles/{first['profile_id']}").status_code == 404
        assert asha.get(f"/api/profiles/{first['profile_id']}").status_code == 200

        # sign out, then sign back in from a "new browser": everything is still there
        assert asha.post("/api/auth/logout").status_code == 204
        assert asha.get("/api/auth/me").status_code == 401
        with TestClient(main.app) as later:
            assert later.post("/api/auth/login", json={"email": "ASHA@example.com", "password": "s3cret-pass"}).status_code == 200
            assert later.get("/api/me/profile").json()["id"] == second["profile_id"]
            assert later.delete(f"/api/me/history/{second['profile_id']}").status_code == 204
            assert later.get("/api/me/profile").json()["id"] == first["profile_id"]

            # deleting the account removes its data and signs out
            assert later.delete("/api/auth/me").status_code == 204
            assert later.get("/api/auth/me").status_code == 401
            assert later.post("/api/auth/login", json={"email": "asha@example.com", "password": "s3cret-pass"}).status_code == 401
        assert ravi.get("/api/auth/me").status_code == 200


def test_old_database_is_upgraded(tmp_path):
    """A database created before accounts existed gains the new columns at startup."""
    import asyncio
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE user_profiles (id VARCHAR(36) PRIMARY KEY, created_at DATETIME, technical_skills JSON, "
                "soft_skills JSON, interests JSON, education_level VARCHAR(20), years_experience FLOAT, bio TEXT)")
    con.commit()
    con.close()

    async def upgrade():
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        async with engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
            await conn.run_sync(db._add_missing_columns)
            await conn.run_sync(db._add_missing_columns)          # safe to run twice
        await engine.dispose()

    asyncio.run(upgrade())
    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(user_profiles)")}
    assert {"user_id", "result"} <= columns


# --------------------------------------------------------------------------- ML classifier
def test_classifier_training_and_prediction(tmp_path):
    import ml_model

    careers = db.load_careers_csv(BACKEND / "data" / "careers.csv")
    rows, labels = ml_model.generate_profiles(careers, per_career=10)
    assert len(rows) == len(labels) == 10 * len(careers) and len(set(labels)) == len(careers)
    assert rows == ml_model.generate_profiles(careers, per_career=10)[0]          # reproducible

    path = tmp_path / "model.joblib"
    classifier = ml_model.load_or_train(careers, path, per_career=40)
    assert path.exists() and path.with_suffix(".metrics.json").exists()
    report = classifier.report
    assert set(report["comparison"]) == {"Logistic Regression", "Random Forest", "Naive Bayes (Bernoulli)"}
    assert report["selected"] == min(report["comparison"], key=lambda n: report["comparison"][n]["log_loss"])
    assert classifier.info["top3_accuracy"] > 0.8

    probabilities = classifier.predict_proba(
        {normalize_skill(s) for s in ["React", "JS", "TypeScript", "HTML", "CSS", "Figma"]}, "bachelor", 1)
    assert abs(sum(probabilities.values()) - 1) < 1e-6 and len(probabilities) == len(careers)
    assert max(probabilities, key=probabilities.get) in {"frontend-developer", "full-stack-developer"}
    assert classifier.predict_proba({"basket weaving"}, "bachelor", 0)            # unknown skills do not crash

    # reloads instead of retraining while the dataset is unchanged; retrains when it changes
    assert ml_model.load_or_train(careers, path).info["trained_at"] == classifier.info["trained_at"]
    changed = [dict(c) for c in careers]
    changed[0]["required_skills"] = changed[0]["required_skills"] + ["Rust"]
    assert ml_model.dataset_fingerprint(changed) != ml_model.dataset_fingerprint(careers)


def test_api_uses_classifier(client):
    meta = client.get("/api/meta").json()
    assert meta["engine"]["classifier"]["name"] in {"Logistic Regression", "Random Forest", "Naive Bayes (Bernoulli)"}
    report = client.get("/api/model").json()
    assert report["samples"]["careers"] >= 50 and "model" not in report
    body = client.post("/api/recommend", json={"technical_skills": ["React", "TypeScript", "CSS", "HTML"],
                                               "education_level": "bachelor", "save_profile": False}).json()
    top = body["recommendations"][0]
    assert top["score_breakdown"]["weights"]["model_fit"] == 0.2
    assert 0 <= top["model_probability"] <= 1 and top["score_breakdown"]["model_fit"] is not None


# --------------------------------------------------------------------------- dense backend path
class FakeDenseBackend:
    """Stands in for Sentence-Transformers: any backend returning unit-length dense rows works."""
    name, model = "fake-dense", "hashed-bag-of-words"

    def fit(self, corpus):
        return None

    def encode(self, texts):
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                out[row, sum(map(ord, token)) % 256] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


def test_recommender_is_backend_agnostic():
    careers = db.load_careers_csv(BACKEND / "data" / "careers.csv")
    recommender = CareerRecommender(careers, FakeDenseBackend())
    result = recommender.recommend(ProfileInput(
        technical_skills=["Network Security", "SIEM", "Incident Response", "Linux", "Networking"],
        education_level="bachelor", years_experience=2), top_k=3)
    assert result["engine"]["backend"] == "fake-dense"
    assert result["recommendations"][0]["career"]["title"] == "Cybersecurity Analyst"
