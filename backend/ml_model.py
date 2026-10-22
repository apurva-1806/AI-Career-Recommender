"""Supervised ML model: a classifier that predicts which career a skill profile belongs to.

Why a generated training set
----------------------------
There is no labelled data of real people and the careers they chose, so the training set is
generated from the career dataset itself. Each synthetic profile starts from one career's skill
list and is then made realistic:

* a random share of the required skills is dropped (people rarely list everything),
* a few preferred skills and strengths are added at random,
* about a third of profiles also carry part of a second career's skills (mixed backgrounds,
  career changers), and one to four unrelated skills are mixed in as noise,
* education and years of experience vary around the role's usual level.

Several classifiers are trained on the same split. The one with the lowest log loss on the
held-out test set is kept, because the recommender uses the predicted probabilities, not just
the top label. Those scores measure how well the model learned the dataset; they
are not a measure of how good real-world career advice is.

Features: one binary column per known skill or strength, plus education level and years of
experience scaled to 0-1.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, log_loss, top_k_accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import BernoulliNB

from model import EDUCATION_LEVELS, SkillTaxonomy, normalize_skill

logger = logging.getLogger("career.ml")

BUNDLE_VERSION = 1
RANDOM_STATE = 42


def dataset_fingerprint(careers: Sequence[dict]) -> str:
    """Changes whenever the parts of the dataset the model learns from change."""
    relevant = sorted(
        (c["id"], c["required_skills"], c.get("preferred_skills", []), c.get("traits", []),
         c["education_level"], c["min_experience_years"])
        for c in careers)
    return hashlib.sha256(json.dumps(relevant).encode("utf-8")).hexdigest()


class SkillFeaturizer:
    """Turns (skills, education, years) into a fixed-length numeric vector."""

    def __init__(self, vocabulary: Iterable[str]):
        self.vocabulary = sorted(set(vocabulary))
        self.index = {skill: i for i, skill in enumerate(self.vocabulary)}

    @property
    def n_features(self) -> int:
        return len(self.vocabulary) + 2

    def transform(self, rows: Sequence[tuple[set[str], str, float]]) -> np.ndarray:
        matrix = np.zeros((len(rows), self.n_features), dtype=np.float32)
        for r, (skills, education, years) in enumerate(rows):
            for skill in skills:
                j = self.index.get(skill)
                if j is not None:
                    matrix[r, j] = 1.0
            matrix[r, -2] = EDUCATION_LEVELS.get(education, EDUCATION_LEVELS["bachelor"])["rank"] / 4
            matrix[r, -1] = min(max(float(years), 0.0), 20.0) / 20
        return matrix


def generate_profiles(careers: Sequence[dict], per_career: int = 80,
                      seed: int = RANDOM_STATE) -> tuple[list[tuple[set[str], str, float]], list[str]]:
    """Build a labelled training set of realistic, noisy profiles from the career dataset."""
    rng = np.random.default_rng(seed)
    taxonomy = SkillTaxonomy(careers)
    required = [[normalize_skill(s) for s in c["required_skills"]] for c in careers]
    preferred = [[normalize_skill(s) for s in c.get("preferred_skills", [])] for c in careers]
    traits = [[normalize_skill(s) for s in c.get("traits", [])] for c in careers]
    vocabulary = sorted({s for group in (required, preferred, traits) for skills in group for s in skills})
    ranks = {value["rank"]: key for key, value in EDUCATION_LEVELS.items()}

    rows, labels = [], []
    for i, career in enumerate(careers):
        base_rank = EDUCATION_LEVELS[career["education_level"]]["rank"]
        for _ in range(per_career):
            keep = rng.uniform(0.2, 0.85)
            skills = {s for s in required[i] if rng.random() < keep}
            if rng.random() < 0.35:                       # mixed background / career changer
                other = int(rng.integers(len(careers)))
                share = rng.uniform(0.15, 0.5)
                skills |= {s for s in required[other] if rng.random() < share}
            pref_rate, trait_rate = rng.uniform(0.05, 0.6), rng.uniform(0.15, 0.7)
            skills |= {s for s in preferred[i] if rng.random() < pref_rate}
            skills |= {s for s in traits[i] if rng.random() < trait_rate}
            noise = min(int(rng.poisson(2.0)), 5)
            if noise:
                skills |= set(rng.choice(vocabulary, size=noise, replace=False).tolist())
            while len(skills) < 2:
                skills.add(str(rng.choice(required[i])))
            rank = int(np.clip(base_rank + rng.choice([-1, 0, 0, 0, 1]), 0, 4))
            years = max(0.0, career["min_experience_years"] + rng.normal(1.0, 2.0))
            rows.append((taxonomy.expand(skills), ranks[rank], round(years, 1)))
            labels.append(career["id"])
    return rows, labels


def _candidates() -> dict[str, object]:
    return {
        "Logistic Regression": LogisticRegression(max_iter=3000, C=2.0),
        "Random Forest": RandomForestClassifier(n_estimators=150, n_jobs=-1, random_state=RANDOM_STATE),
        "Naive Bayes (Bernoulli)": BernoulliNB(alpha=0.5, binarize=0.5),
    }


class CareerClassifier:
    """A trained classifier plus everything needed to use and describe it."""

    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.model = bundle["model"]
        self.featurizer: SkillFeaturizer = bundle["featurizer"]
        self.classes: list[str] = list(self.model.classes_)

    # ------------------------------------------------------------------ training
    @classmethod
    def train(cls, careers: Sequence[dict], per_career: int = 80, test_size: float = 0.2) -> "CareerClassifier":
        rows, labels = generate_profiles(careers, per_career)
        featurizer = SkillFeaturizer(v for skills, _, _ in rows for v in skills)
        X, y = featurizer.transform(rows), np.array(labels)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=RANDOM_STATE)

        results = {}
        for name, estimator in _candidates().items():
            started = time.perf_counter()
            estimator.fit(X_train, y_train)
            seconds = time.perf_counter() - started
            proba = estimator.predict_proba(X_test)
            predicted = estimator.classes_[proba.argmax(axis=1)]
            results[name] = {
                "accuracy": round(float(accuracy_score(y_test, predicted)), 4),
                "top3_accuracy": round(float(top_k_accuracy_score(y_test, proba, k=3, labels=estimator.classes_)), 4),
                "macro_f1": round(float(f1_score(y_test, predicted, average="macro")), 4),
                "log_loss": round(float(log_loss(y_test, proba, labels=estimator.classes_)), 4),
                "train_seconds": round(seconds, 2),
            }
            logger.info("%s: %s", name, results[name])

        best = min(results, key=lambda n: (results[n]["log_loss"], -results[n]["top3_accuracy"]))
        final = _candidates()[best]
        final.fit(X, y)          # refit the winner on all generated data
        bundle = {
            "version": BUNDLE_VERSION,
            "sklearn_version": sklearn.__version__,
            "fingerprint": dataset_fingerprint(careers),
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "selected": best,
            "comparison": results,
            "samples": {"total": int(len(y)), "train": int(len(y_train)), "test": int(len(y_test)),
                        "per_career": per_career, "careers": len(careers),
                        "features": featurizer.n_features},
            "model": final,
            "featurizer": featurizer,
        }
        return cls(bundle)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.bundle, path)
        public = {k: v for k, v in self.bundle.items() if k not in {"model", "featurizer"}}
        path.with_suffix(".metrics.json").write_text(json.dumps(public, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ inference
    def predict_proba(self, skills: set[str], education: str, years: float) -> dict[str, float]:
        """Probability for every career id, given canonical skill names."""
        vector = self.featurizer.transform([(skills, education, years)])
        probabilities = self.model.predict_proba(vector)[0]
        return dict(zip(self.classes, (float(p) for p in probabilities)))

    @property
    def info(self) -> dict:
        chosen = self.bundle["comparison"][self.bundle["selected"]]
        return {
            "name": self.bundle["selected"],
            "accuracy": chosen["accuracy"],
            "top3_accuracy": chosen["top3_accuracy"],
            "macro_f1": chosen["macro_f1"],
            "log_loss": chosen["log_loss"],
            "training_samples": self.bundle["samples"]["total"],
            "trained_at": self.bundle["trained_at"],
        }

    @property
    def report(self) -> dict:
        return {k: v for k, v in self.bundle.items() if k not in {"model", "featurizer"}}


def load_or_train(careers: Sequence[dict], path: Path, per_career: int = 80,
                  force: bool = False) -> CareerClassifier:
    """Load the saved model if it matches this dataset and scikit-learn version; otherwise retrain."""
    fingerprint = dataset_fingerprint(careers)
    if path.exists() and not force:
        try:
            bundle = joblib.load(path)
            if (bundle.get("version") == BUNDLE_VERSION and bundle.get("fingerprint") == fingerprint
                    and bundle.get("sklearn_version") == sklearn.__version__):
                logger.info("Loaded career classifier from %s", path)
                return CareerClassifier(bundle)
            logger.info("Saved classifier is out of date; retraining.")
        except Exception as exc:   # corrupt file, incompatible pickle, etc.
            logger.warning("Could not load %s (%s); retraining.", path, exc)

    logger.info("Training career classifier on generated profiles")
    classifier = CareerClassifier.train(careers, per_career)
    classifier.save(path)
    logger.info("Selected %s: %s", classifier.info["name"], classifier.info)
    return classifier
