"""NLP pipeline and content-based recommendation engine.

Pipeline
--------
1. Clean and tokenise free text (skills, interests, bio / resume).
2. Normalise skills against a taxonomy (aliases such as "js" -> "javascript", plus
   implied skills such as "postgresql" -> "sql") and pull known skills out of free text.
3. Embed the user profile and every career profile into one vector space, using
   Sentence-Transformers (default: all-MiniLM-L6-v2) or TF-IDF as a fallback.
4. Score each career:

       match = 0.50 * semantic_fit + 0.40 * skill_fit + 0.10 * readiness

   or, when the trained ML classifier (ml_model.py) is loaded:

       match = 0.40 * semantic_fit + 0.30 * skill_fit + 0.20 * model_fit + 0.10 * readiness

   * semantic_fit - cosine similarity between user and career vectors, divided by the
     similarity an "ideal" candidate (someone listing exactly that career's skills and
     traits) would get. Raw cosine values are small and differ between embedding
     backends; this calibration turns them into a comparable 0-1 scale.
   * skill_fit    - weighted share of required (1.0) and preferred (0.4) skills covered.
   * readiness    - how the user's experience and education compare with the typical bar.
   * model_fit    - the classifier's predicted probability for the career, divided by its
     probability for its own top choice (1.0 = the model's first pick).
5. Return the top K careers with a skill-gap analysis and learning plan.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol, Sequence
from urllib.parse import quote_plus

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

logger = logging.getLogger("career.model")

# --------------------------------------------------------------------------- constants
WEIGHT_SEMANTIC = 0.50
WEIGHT_SKILLS = 0.40
WEIGHT_READINESS = 0.10
# Weights used when the supervised classifier is available
WEIGHTS_WITH_MODEL = {"semantic_fit": 0.40, "skill_fit": 0.30, "model_fit": 0.20, "readiness": 0.10}
PREFERRED_SKILL_WEIGHT = 0.4
STRUCTURED_VS_BIO = 0.7          # share of the user vector that comes from skills/interests

EDUCATION_LEVELS: dict[str, dict] = {
    "high_school": {"rank": 0, "label": "High school"},
    "associate": {"rank": 1, "label": "Associate degree or diploma"},
    "bachelor": {"rank": 2, "label": "Bachelor's degree"},
    "master": {"rank": 3, "label": "Master's degree"},
    "doctorate": {"rank": 4, "label": "Doctorate"},
}

# alias -> canonical skill name (all lower-case)
SKILL_ALIASES: dict[str, str] = {
    "js": "javascript", "es6": "javascript", "ecmascript": "javascript",
    "ts": "typescript",
    "reactjs": "react", "react.js": "react",
    "nextjs": "next.js", "next": "next.js",
    "node": "node.js", "nodejs": "node.js",
    "html5": "html", "css3": "css", "tailwind": "tailwind css", "tailwindcss": "tailwind css",
    "py": "python", "python3": "python",
    "golang": "go", "cpp": "c++", "csharp": "c#", "c sharp": "c#",
    "r programming": "r", "rstats": "r",
    "postgres": "postgresql", "mongo": "mongodb",
    "ml": "machine learning", "dl": "deep learning",
    "natural language processing": "nlp", "cv": "computer vision",
    "llm": "large language models", "llms": "large language models",
    "generative ai": "large language models", "genai": "large language models",
    "sklearn": "scikit-learn", "scikit learn": "scikit-learn", "torch": "pytorch", "tf": "tensorflow",
    "spark": "apache spark", "pyspark": "apache spark", "apache airflow": "airflow",
    "apache kafka": "kafka",
    "k8s": "kubernetes", "amazon web services": "aws", "google cloud": "gcp",
    "google cloud platform": "gcp", "microsoft azure": "azure",
    "ci cd": "ci/cd", "cicd": "ci/cd", "continuous integration": "ci/cd",
    "rest": "rest apis", "rest api": "rest apis", "restful apis": "rest apis", "api design": "rest apis",
    "apis": "rest apis",
    "dsa": "data structures & algorithms", "algorithms": "data structures & algorithms",
    "data structures": "data structures & algorithms",
    "data structures and algorithms": "data structures & algorithms",
    "data viz": "data visualization", "data visualisation": "data visualization",
    "dataviz": "data visualization",
    "powerbi": "power bi", "ms excel": "excel", "microsoft excel": "excel", "spreadsheets": "excel",
    "data analytics": "data analysis", "analytics": "data analysis",
    "stats": "statistics", "maths": "mathematics", "math": "mathematics",
    "ab testing": "a/b testing", "a/b tests": "a/b testing", "experimentation design": "experiment design",
    "data modelling": "data modeling", "financial modelling": "financial modeling",
    "ux": "ux design", "user experience": "ux design", "user experience design": "ux design",
    "ui": "ui design", "user interface design": "ui design",
    "photoshop": "adobe photoshop", "illustrator": "adobe illustrator", "indesign": "adobe indesign",
    "unit testing": "testing", "test automation": "testing", "qa": "testing",
    "pentesting": "penetration testing", "pen testing": "penetration testing",
    "ethical hacking": "penetration testing", "infosec": "network security",
    "cybersecurity": "network security", "cyber security": "network security",
    "seo optimization": "seo", "search engine optimization": "seo",
    "social media marketing": "social media", "ppc": "paid advertising", "google ads": "paid advertising",
    "pm": "project management", "scrum master": "scrum",
    "product management": "product strategy",
    "stakeholder communication": "stakeholder management",
    "problem solving": "problem-solving", "decision making": "decision-making",
    "teamwork": "collaboration", "team work": "collaboration", "team player": "collaboration",
    "analytical": "analytical thinking", "analytical skills": "analytical thinking",
    "detail oriented": "attention to detail", "detail-oriented": "attention to detail",
    "ai": "ai research", "artificial intelligence": "ai research",
    "story telling": "storytelling", "mentorship": "mentoring", "coaching others": "mentoring",
    "leading teams": "leadership", "team leadership": "leadership",
    "creative thinking": "creativity", "time-management": "time management",
    "written communication": "writing", "verbal communication": "communication",
}

# having the key implies the values (used only for skill coverage, not shown as user input)
SKILL_IMPLIES: dict[str, tuple[str, ...]] = {
    "postgresql": ("sql",), "mysql": ("sql",), "snowflake": ("sql",), "dbt": ("sql",),
    "pandas": ("python",), "scikit-learn": ("python", "machine learning"),
    "pytorch": ("python", "deep learning"), "tensorflow": ("python", "deep learning"),
    "fastapi": ("python", "rest apis"), "django": ("python",), "flask": ("python",),
    "transformers": ("deep learning", "nlp"), "deep learning": ("machine learning",),
    "react": ("javascript",), "next.js": ("react", "javascript"), "node.js": ("javascript",),
    "typescript": ("javascript",), "react native": ("javascript",),
    "tailwind css": ("css",), "kubernetes": ("docker",),
    "tableau": ("data visualization",), "power bi": ("data visualization",),
    "scrum": ("agile",), "unity": ("c#",), "unreal engine": ("c++",),
}

# Terms too ambiguous to pull out of free prose (they still count when typed as a skill).
FREE_TEXT_SKIP = {
    "go", "r", "c", "education", "organization", "design", "research", "finance", "writing",
    "strategy", "windows", "hardware", "mechanics", "sourcing", "scheduling", "onboarding",
    "editing", "renewals", "next", "rest", "pm", "ts", "tf", "cv", "ai", "ml", "dl", "ui", "ux",
    "node", "spark", "torch", "stats", "math", "analytics", "apis", "algorithms", "qa", "py",
}

_URL = re.compile(r"https?://\S+|www\.\S+")
_EMAIL = re.compile(r"\S+@\S+\.\S+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_TOKEN = re.compile(r"[a-z][a-z0-9+#]*(?:[./][a-z0-9+#]+)*")
_KEEP_SINGLE = {"c", "r"}


# --------------------------------------------------------------------------- text utilities
def clean_text(text: str | None) -> str:
    """Lower-case, strip URLs / e-mails / phone numbers and collapse whitespace."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = _URL.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _PHONE.sub(" ", text)
    text = text.replace("’", "'").replace("&", " and ")
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str | None) -> list[str]:
    """Tokenise cleaned text, keeping technical tokens such as c++, c#, node.js and ci/cd."""
    tokens = []
    for token in _TOKEN.findall(clean_text(text)):
        if token in ENGLISH_STOP_WORDS:
            continue
        if len(token) == 1 and token not in _KEEP_SINGLE:
            continue
        tokens.append(token)
    return tokens


def normalize_skill(raw: str | None) -> str:
    """Map a user-typed skill to its canonical lower-case name."""
    skill = unicodedata.normalize("NFKC", raw or "").lower().strip()
    skill = re.sub(r"\s+", " ", skill).strip(" .,;:")
    return SKILL_ALIASES.get(skill, skill)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item:
            seen.setdefault(item, None)
    return list(seen)


def _join(items: Sequence[str], limit: int = 3) -> str:
    items = list(items)[:limit]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _chunk_words(text: str, size: int = 160, max_chunks: int = 8) -> list[str]:
    words = text.split()
    chunks = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    return chunks[:max_chunks]


def outlook_label(growth_pct: float) -> str:
    if growth_pct >= 15:
        return "Much faster than average"
    if growth_pct >= 8:
        return "Faster than average"
    if growth_pct >= 4:
        return "About average"
    if growth_pct >= 1:
        return "Slower than average"
    return "Little or no change"


# --------------------------------------------------------------------------- taxonomy
class SkillTaxonomy:
    """Known skills and traits, used for display names and free-text skill extraction."""

    def __init__(self, careers: Sequence[dict]):
        self.display: dict[str, str] = {}
        self.category: dict[str, str] = {}
        for career in careers:
            for column, kind in (("required_skills", "technical"), ("preferred_skills", "technical"),
                                 ("traits", "soft")):
                for raw in career.get(column, []):
                    key = normalize_skill(raw)
                    self.display.setdefault(key, raw)
                    self.category.setdefault(key, kind)

        surface: dict[str, str] = {name: name for name in self.display}
        for alias, target in SKILL_ALIASES.items():
            if target in self.display:
                surface.setdefault(alias, target)
        self._surface = {clean_text(k): v for k, v in surface.items() if k not in FREE_TEXT_SKIP}
        ordered = sorted(self._surface, key=len, reverse=True)
        self._pattern = re.compile(
            r"(?<![a-z0-9+#])(?:" + "|".join(re.escape(term) for term in ordered) + r")(?![a-z0-9+#])")

    def name(self, key: str) -> str:
        """Display name for a canonical key (falls back to the key itself)."""
        return self.display.get(key, key)

    def extract(self, text: str | None) -> list[str]:
        """Return canonical skills/traits mentioned in free text, in order of appearance."""
        cleaned = clean_text(text)
        if not cleaned:
            return []
        return _dedupe(self._surface[m.group(0)] for m in self._pattern.finditer(cleaned))

    def expand(self, skills: Iterable[str]) -> set[str]:
        """Add implied skills (e.g. PostgreSQL implies SQL)."""
        have = set(skills)
        frontier = list(have)
        while frontier:
            for implied in SKILL_IMPLIES.get(frontier.pop(), ()):
                if implied not in have:
                    have.add(implied)
                    frontier.append(implied)
        return have


# --------------------------------------------------------------------------- embedding backends
class EmbeddingBackend(Protocol):
    name: str
    model: str

    def fit(self, corpus: Sequence[str]) -> None: ...
    def encode(self, texts: Sequence[str]) -> np.ndarray: ...   # rows are L2-normalised


def _l2_normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# Section labels used when profiles are rendered as text; they carry no meaning for matching.
_LABEL_WORDS = {"skills", "strengths", "interests"}


def _tfidf_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in _LABEL_WORDS]


class TfidfBackend:
    """Sparse lexical embeddings: TF-IDF over word unigrams.

    Unigrams only: profiles are mostly comma-separated skill lists, so bigrams would mostly
    pair unrelated neighbours ("sql react") and add noise.
    """
    name = "tfidf"
    model = "TF-IDF (unigrams, sublinear tf)"

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            tokenizer=_tfidf_tokens, token_pattern=None, lowercase=False,
            sublinear_tf=True, norm="l2", dtype=np.float32)

    def fit(self, corpus: Sequence[str]) -> None:
        self._vectorizer.fit(corpus)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return _l2_normalise(self._vectorizer.transform(list(texts)).toarray().astype(np.float32))


class SentenceTransformerBackend:
    """Dense semantic embeddings from a Sentence-Transformers model."""
    name = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, done lazily

        self.model = model_name
        self._model = SentenceTransformer(model_name)

    def fit(self, corpus: Sequence[str]) -> None:   # pre-trained: nothing to fit
        return None

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False,
                                     convert_to_numpy=True)
        return _l2_normalise(np.asarray(vectors, dtype=np.float32))


def build_backend(kind: str = "auto", model_name: str = "all-MiniLM-L6-v2") -> EmbeddingBackend:
    """Create the embedding backend. 'auto' prefers Sentence-Transformers, else TF-IDF."""
    kind = (kind or "auto").lower()
    if kind == "tfidf":
        return TfidfBackend()
    if kind not in {"auto", "sbert"}:
        raise ValueError(f"Unknown EMBEDDING_BACKEND '{kind}'. Use auto, sbert or tfidf.")
    try:
        backend = SentenceTransformerBackend(model_name)
        logger.info("Loaded sentence-transformers model %s", model_name)
        return backend
    except Exception as exc:  # missing package, no network for first download, etc.
        if kind == "sbert":
            raise RuntimeError(f"Could not load sentence-transformers model '{model_name}': {exc}") from exc
        logger.warning("sentence-transformers unavailable (%s); falling back to TF-IDF.", exc)
        return TfidfBackend()


# --------------------------------------------------------------------------- recommender
@dataclass
class ProfileInput:
    technical_skills: list[str] = field(default_factory=list)
    soft_skills: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    education_level: str = "bachelor"
    years_experience: float = 0.0
    bio: str = ""


class CareerRecommender:
    """Content-based recommender over a fixed set of career profiles."""

    def __init__(self, careers: Sequence[dict], backend: EmbeddingBackend,
                 resources: dict[str, list[dict]] | None = None, classifier=None):
        if not careers:
            raise ValueError("The career dataset is empty; seed the database first.")
        self.careers = list(careers)
        self.backend = backend
        self.classifier = classifier      # optional ml_model.CareerClassifier
        self.resources = {normalize_skill(k): v for k, v in (resources or {}).items()}
        self.taxonomy = SkillTaxonomy(self.careers)

        self._required = [[normalize_skill(s) for s in c["required_skills"]] for c in self.careers]
        self._preferred = [[normalize_skill(s) for s in c.get("preferred_skills", [])] for c in self.careers]
        self._traits = [[normalize_skill(s) for s in c.get("traits", [])] for c in self.careers]

        documents = [self._career_document(c) for c in self.careers]
        self.backend.fit(documents)
        self._career_vectors = self.backend.encode(documents)

        ideal = [self._structured_text(c["required_skills"] + c.get("preferred_skills", []), c.get("traits", []))
                 for c in self.careers]
        ideal_vectors = self.backend.encode(ideal)
        # similarity an ideal candidate would score against each career (calibration ceiling)
        self._ceiling = np.clip(np.einsum("ij,ij->i", ideal_vectors, self._career_vectors), 0.05, 1.0)

    # ------------------------------------------------------------------ text builders
    @staticmethod
    def _career_document(career: dict) -> str:
        skills = ", ".join(career["required_skills"] + career.get("preferred_skills", []))
        traits = ", ".join(career.get("traits", []))
        return (f"{career['title']}. {career['title']} in {career['industry']}. "
                f"Skills: {skills}. Strengths and interests: {traits}. {career['description']}")

    @staticmethod
    def _structured_text(skills: Sequence[str], traits: Sequence[str]) -> str:
        parts = []
        if skills:
            parts.append("Skills: " + ", ".join(skills) + ".")
        if traits:
            parts.append("Strengths and interests: " + ", ".join(traits) + ".")
        return " ".join(parts)

    @property
    def engine_info(self) -> dict:
        return {"backend": self.backend.name, "model": self.backend.model, "careers_indexed": len(self.careers),
                "classifier": self.classifier.info if self.classifier else None}

    # ------------------------------------------------------------------ embedding the user
    def _embed_user(self, structured: str, bio: str) -> np.ndarray:
        dim = self._career_vectors.shape[1]
        vector = np.zeros(dim, dtype=np.float32)
        if structured:
            vector += STRUCTURED_VS_BIO * self.backend.encode([structured])[0]
        chunks = _chunk_words(clean_text(bio)) if len(tokenize(bio)) >= 5 else []
        if chunks:
            bio_vector = _l2_normalise(self.backend.encode(chunks).mean(axis=0, keepdims=True))[0]
            vector += (1 - STRUCTURED_VS_BIO if structured else 1.0) * bio_vector
        return _l2_normalise(vector.reshape(1, -1))[0]

    # ------------------------------------------------------------------ scoring helpers
    @staticmethod
    def _readiness(profile: ProfileInput, career: dict) -> tuple[float, list[str]]:
        notes: list[str] = []
        need_years = int(career.get("min_experience_years", 0))
        years = max(0.0, float(profile.years_experience))
        if years >= need_years:
            exp_fit = 1.0
        else:
            exp_fit = (years + 1) / (need_years + 1)
            notes.append(f"Roles usually ask for about {need_years}+ years of experience; "
                         f"you have {years:g}. Treat this as a {max(1, round(need_years - years))}-year goal "
                         f"or look for junior and associate openings.")

        need = EDUCATION_LEVELS.get(career.get("education_level", "bachelor"), EDUCATION_LEVELS["bachelor"])
        have = EDUCATION_LEVELS.get(profile.education_level, EDUCATION_LEVELS["bachelor"])
        gap = need["rank"] - have["rank"]
        if gap <= 0:
            edu_fit = 1.0
        else:
            edu_fit = max(0.0, 1.0 - 0.35 * gap)
            notes.append(f"Typical entry requirement: {need['label'].lower()}. "
                         f"Strong project work or certifications can sometimes stand in for it.")
        return 0.6 * exp_fit + 0.4 * edu_fit, notes

    def _resources_for(self, skill_key: str) -> list[dict]:
        curated = self.resources.get(skill_key)
        if curated:
            return curated[:2]
        name = self.taxonomy.name(skill_key)
        query = quote_plus(name)
        return [
            {"title": f"Courses on {name}", "provider": "Coursera search",
             "url": f"https://www.coursera.org/search?query={query}", "type": "search"},
            {"title": f"Courses on {name}", "provider": "edX search",
             "url": f"https://www.edx.org/search?q={query}", "type": "search"},
        ]

    @staticmethod
    def _confidence(score: float) -> str:
        if score >= 75:
            return "Strong match"
        if score >= 55:
            return "Good match"
        if score >= 35:
            return "Partial match"
        return "Exploratory"

    def _explain(self, career: dict, matched: list[str], required_total: int,
                 matched_traits: list[str], missing: list[str]) -> str:
        name = self.taxonomy.name
        sentences = []
        if matched:
            sentences.append(
                f"You already have {len(matched)} of the {required_total} core skills for this role, "
                f"including {_join([name(s) for s in matched])}.")
        else:
            sentences.append(
                "None of the core skills are on your profile yet; this role appears because your "
                "interests and background read close to its description.")
        if matched_traits:
            sentences.append(f"Your strengths in {_join([name(t) for t in matched_traits])} suit the day-to-day work.")
        if missing:
            sentences.append(f"To be competitive, build {_join([name(s) for s in missing])} next.")
        else:
            sentences.append("You cover every core skill listed, so focus on depth and evidence of impact.")
        return " ".join(sentences)

    # ------------------------------------------------------------------ public API
    def analyse_profile(self, profile: ProfileInput) -> dict:
        """Normalise the profile and return the skills detected in the free-text bio."""
        typed_skills = _dedupe(normalize_skill(s) for s in profile.technical_skills)
        typed_traits = _dedupe(normalize_skill(s) for s in [*profile.soft_skills, *profile.interests])
        typed = set(typed_skills) | set(typed_traits)
        detected = [s for s in self.taxonomy.extract(profile.bio) if s not in typed]
        have = self.taxonomy.expand(typed | set(detected))
        return {"typed_skills": typed_skills, "typed_traits": typed_traits, "detected": detected, "have": have}

    def recommend(self, profile: ProfileInput, top_k: int = 5) -> dict:
        analysis = self.analyse_profile(profile)
        have: set[str] = analysis["have"]
        name = self.taxonomy.name

        detected_technical = [s for s in analysis["detected"] if self.taxonomy.category.get(s) == "technical"]
        detected_soft = [s for s in analysis["detected"] if self.taxonomy.category.get(s) == "soft"]
        structured = self._structured_text(
            [name(s) for s in analysis["typed_skills"] + detected_technical],
            [name(s) for s in analysis["typed_traits"] + detected_soft])
        user_vector = self._embed_user(structured, profile.bio)
        similarities = self._career_vectors @ user_vector            # cosine (rows are unit length)

        probabilities: dict[str, float] = {}
        if self.classifier is not None:
            probabilities = self.classifier.predict_proba(have, profile.education_level, profile.years_experience)
        top_probability = max(probabilities.values(), default=0.0)

        scored = []
        for i, career in enumerate(self.careers):
            required, preferred, traits = self._required[i], self._preferred[i], self._traits[i]
            matched = [s for s in required if s in have]
            missing = [s for s in required if s not in have]
            matched_pref = [s for s in preferred if s in have]
            missing_pref = [s for s in preferred if s not in have]

            weight_total = len(required) + PREFERRED_SKILL_WEIGHT * len(preferred)
            skill_fit = (len(matched) + PREFERRED_SKILL_WEIGHT * len(matched_pref)) / weight_total if weight_total else 0.0
            similarity = float(max(0.0, similarities[i]))
            semantic_fit = min(1.0, similarity / float(self._ceiling[i]))
            readiness, notes = self._readiness(profile, career)
            if probabilities:
                probability = probabilities.get(career["id"], 0.0)
                model_fit = probability / top_probability if top_probability > 0 else 0.0
                w = WEIGHTS_WITH_MODEL
                score = 100 * (w["semantic_fit"] * semantic_fit + w["skill_fit"] * skill_fit
                               + w["model_fit"] * model_fit + w["readiness"] * readiness)
            else:
                probability = model_fit = None
                score = 100 * (WEIGHT_SEMANTIC * semantic_fit + WEIGHT_SKILLS * skill_fit + WEIGHT_READINESS * readiness)
            scored.append((score, i, similarity, semantic_fit, skill_fit, readiness, notes, probability, model_fit,
                           matched, missing, matched_pref, missing_pref, [t for t in traits if t in have]))

        scored.sort(key=lambda row: (-row[0], self.careers[row[1]]["title"]))
        recommendations = []
        for rank, row in enumerate(scored[:max(1, top_k)], start=1):
            (score, i, similarity, semantic_fit, skill_fit, readiness, notes, probability, model_fit,
             matched, missing, matched_pref, missing_pref, matched_traits) = row
            career = self.careers[i]
            plan = [{"skill": name(s), "priority": "core", "resources": self._resources_for(s)} for s in missing]
            plan += [{"skill": name(s), "priority": "bonus", "resources": self._resources_for(s)}
                     for s in missing_pref[:3]]
            recommendations.append({
                "rank": rank,
                "career": {
                    "id": career["id"], "title": career["title"], "industry": career["industry"],
                    "description": career["description"],
                    "education_level": career["education_level"],
                    "education_label": EDUCATION_LEVELS.get(career["education_level"], {}).get("label", ""),
                    "min_experience_years": career["min_experience_years"],
                    "salary": {"min": career["salary_min"], "max": career["salary_max"],
                               "currency": career.get("currency", "INR")},
                    "growth": {"pct": career["growth_pct"], "outlook": outlook_label(career["growth_pct"]),
                               "note": career.get("outlook_note", "")},
                    "certifications": career.get("certifications", []),
                },
                "match_score": round(score, 1),
                "confidence": self._confidence(score),
                "semantic_similarity": round(similarity, 4),
                "skill_coverage": round(len(matched) / len(self._required[i]), 4) if self._required[i] else 0.0,
                "score_breakdown": {
                    "semantic_fit": round(semantic_fit, 4), "skill_fit": round(skill_fit, 4),
                    "readiness": round(readiness, 4),
                    "model_fit": None if model_fit is None else round(model_fit, 4),
                    "weights": dict(WEIGHTS_WITH_MODEL) if probabilities else {
                        "semantic_fit": WEIGHT_SEMANTIC, "skill_fit": WEIGHT_SKILLS, "readiness": WEIGHT_READINESS},
                },
                "model_probability": None if probability is None else round(probability, 4),
                "why": self._explain(career, matched, len(self._required[i]), matched_traits, missing),
                "matched_skills": [name(s) for s in matched],
                "missing_skills": [name(s) for s in missing],
                "matched_preferred": [name(s) for s in matched_pref],
                "missing_preferred": [name(s) for s in missing_pref],
                "matched_traits": [name(t) for t in matched_traits],
                "readiness_notes": notes,
                "learning_plan": plan,
            })

        return {
            "engine": self.engine_info,
            "detected_skills": [name(s) for s in analysis["detected"]],
            "recommendations": recommendations,
        }


def load_resources(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        logger.warning("Learning resources file %s not found; using search links only.", path)
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
