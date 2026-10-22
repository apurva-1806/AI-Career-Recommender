# AI Career Recommendation System

A full-stack app that recommends careers from a person's skills, interests, education,
experience and optional resume text. It uses content-based filtering: the user profile and
160 career profiles are embedded into one vector space and ranked by similarity, then each
match is explained with a skill-gap analysis, a learning roadmap and market data.

| Layer | Stack |
| --- | --- |
| Frontend | React 18, Vite, Tailwind CSS |
| Backend | Python, FastAPI (async), Pydantic v2 |
| NLP / ML | sentence-transformers (`all-MiniLM-L6-v2`) with a scikit-learn TF-IDF fallback; a supervised scikit-learn classifier (Logistic Regression, Random Forest or Naive Bayes, chosen automatically); NumPy, Pandas |
| Database | SQLite for local development, PostgreSQL in production (SQLAlchemy 2 async) |

## Project structure

```
backend/
  main.py                  FastAPI application and routes
  auth.py                  Password hashing, session cookies, current-user dependencies
  model.py                 Text cleaning, skill taxonomy, embeddings, scoring, gap analysis
  ml_model.py              Supervised classifier: training data generation, model comparison, prediction
  train_model.py           Retrain the classifier and print the comparison table
  models/                  Saved classifier and its metrics (created automatically, not in git)
  database.py              SQLAlchemy models, async session setup, dataset seeding
  schemas.py               Request and response models
  resume.py                Text extraction from PDF, DOCX, TXT and MD uploads
  config.py                Settings read from environment variables / .env
  seed.py                  Create tables and load the dataset (also runs automatically)
  data/
    careers.csv            160 career paths across 28 fields: title, industry, skills, traits, salary, growth
    learning_resources.json  Curated learning links per skill
    build_dataset.py       Regenerates careers.csv from readable definitions
  tests/test_api.py        End-to-end tests
  requirements.txt         Core dependencies
  requirements-ml.txt      sentence-transformers (semantic embeddings)
  requirements-postgres.txt  asyncpg, only for PostgreSQL
frontend/
  src/
    App.jsx                Navigation, views (#/, #/profile, #/results) and state
    api.js                 API client
    index.css              Tailwind layers, component classes, dark theme
    components/
      Landing.jsx          Landing page: hero with live example, features, steps,
                           career library, FAQ, call to action
      ProfileForm.jsx      Four-step profile builder
      SkillInput.jsx       Tag input with suggestions
      Dashboard.jsx        Results page and market comparison
      CareerCard.jsx       Match card with score and skill strip
      CareerDetail.jsx     Fit explanation, skill gap, roadmap, salary and outlook
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- About 2 GB of free disk space if you install the sentence-transformers engine

## 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install -r requirements.txt      # API, database, TF-IDF engine
pip install -r requirements-ml.txt   # semantic engine (all-MiniLM-L6-v2); recommended

cp .env.example .env                 # optional: every setting has a default
python seed.py                       # creates career.db and loads the 160 careers
uvicorn main:app --reload --port 8000
```

The API is now at http://localhost:8000 and its interactive docs at http://localhost:8000/docs.

Notes:

- `python seed.py` is optional on first run, because the server creates the tables and loads
  the dataset at startup when the database is empty. Use `python seed.py --reset` after
  editing `data/careers.csv`; it drops all tables, including accounts and saved profiles,
  and reloads.
- On first start with sentence-transformers installed, the model (about 90 MB) downloads from
  Hugging Face. That needs internet access once; afterwards it is cached.
- Check which engine is active at http://localhost:8000/api/health. `"backend"` reads
  `sentence-transformers` or `tfidf`.

### Choosing the embedding engine

Set `EMBEDDING_BACKEND` in `backend/.env`:

| Value | Behaviour |
| --- | --- |
| `auto` (default) | Use sentence-transformers if it is installed and the model loads; otherwise fall back to TF-IDF and log a warning |
| `sbert` | Require sentence-transformers; startup fails if it cannot load |
| `tfidf` | Use scikit-learn TF-IDF only. No model download, starts instantly |

TF-IDF matches on shared words, so it scores lower and misses synonyms ("statistical
modelling" versus "machine learning"). The sentence-transformers engine matches on meaning
and is the better choice whenever you can install it.

### Using PostgreSQL

```bash
pip install -r requirements-postgres.txt
createdb career
```

Then set in `backend/.env`:

```
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/career
```

Start the server as before. Tables are created and seeded on first start.

## 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The landing page loads its example result and career library
from the API, so start the backend first. Colours and fonts are defined in
`tailwind.config.js` and `src/index.css`. The Vite dev server proxies `/api` to `http://localhost:8000`,
so no extra configuration is needed. For a production build run `npm run build` (output in
`frontend/dist`) and set `VITE_API_URL` to the API's address at build time; add that site's
origin to `CORS_ORIGINS` in the backend.

## 3. Tests

```bash
cd backend
pytest -q
```

The tests run against a temporary SQLite database with the TF-IDF engine, so they need no
network access.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Status and active embedding engine |
| GET | `/api/meta` | Skill suggestions, education levels, industries |
| GET | `/api/model` | How the ML classifier was trained and how each algorithm scored |
| GET | `/api/careers?industry=&q=` | Browse or search the career dataset |
| GET | `/api/careers/{id}` | One career |
| POST | `/api/resume/parse` | Upload a resume; returns its text and the skills found in it |
| POST | `/api/recommend?top_k=5` | Rank careers for a profile |
| GET | `/api/profiles/{id}` | A stored profile and its recommendations (owner only if it belongs to an account) |
| POST | `/api/auth/register` | Create an account and sign in |
| POST | `/api/auth/login` | Sign in |
| POST | `/api/auth/logout` | Sign out |
| GET | `/api/auth/me` | The signed-in user |
| DELETE | `/api/auth/me` | Delete the account and everything saved in it |
| GET | `/api/me/profile` | Newest saved profile with its full results, or `null` |
| GET | `/api/me/history` | Saved runs, newest first |
| GET | `/api/me/history/{id}` | One saved run with its full results |
| DELETE | `/api/me/history/{id}` | Delete one saved run |

Example:

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "technical_skills": ["Python", "React", "Data Analysis", "SQL"],
    "soft_skills": ["Leadership", "Problem-solving"],
    "interests": ["Creative writing", "AI research"],
    "education_level": "bachelor",
    "years_experience": 2,
    "bio": "Analyst who builds dashboards and automates reports."
  }'
```

`education_level` is one of `high_school`, `associate`, `bachelor`, `master`, `doctorate`.
Send `"save_profile": false` to get recommendations without storing anything.

## Saved profile and results

The website has no sign-in. The profile and the latest results are remembered in the
visitor's own browser (localStorage), so reopening the site on the same device shows them
again without rebuilding anything. "Start over" clears them. They are not shared across
devices or browsers.

The backend still contains account endpoints (`/api/auth/*`, `/api/me/*`) and their tables
from an earlier version. The website no longer uses them, and they can be deleted
(`auth.py` and those routes in `main.py`) without affecting anything else.

## How the recommendation engine works

1. **Clean and tokenise.** Text is lower-cased; URLs, e-mail addresses and phone numbers are
   removed; technical tokens such as `c++`, `c#`, `node.js` and `ci/cd` are kept intact.
2. **Normalise skills.** Aliases map to canonical names (`js` to JavaScript, `k8s` to
   Kubernetes). Some skills imply others (PostgreSQL implies SQL, PyTorch implies deep
   learning). Known skills are also extracted from the bio or resume text.
3. **Embed.** Each career becomes one document (title, industry, skills, traits,
   description). The user profile becomes a vector that is 70% skills and interests and
   30% bio text, so a long resume cannot drown out the skills that were listed.
4. **Predict with the ML classifier.** A supervised model (see below) predicts a probability
   for every career from the skills, education and experience on the profile.
5. **Score.** For every career:

   ```
   match = 0.40 * semantic_fit + 0.30 * skill_fit + 0.20 * model_fit + 0.10 * readiness
   ```

   - `semantic_fit` is the cosine similarity between the user and career vectors, divided by
     the similarity an ideal candidate would get (someone listing exactly that career's
     skills and traits). Raw cosine values are small and differ between engines; this puts
     them on a 0 to 1 scale. The raw cosine is also returned as `semantic_similarity`.
   - `skill_fit` is the weighted share of skills covered: required skills count 1.0,
     preferred skills 0.4.
   - `model_fit` is the classifier's probability for the career divided by the probability of
     its top choice, so the model's first pick scores 1.0. The raw probability is returned as
     `model_probability`.
   - `readiness` compares years of experience and education level with the typical
     requirement for the role.

   With `USE_CLASSIFIER=0` the classifier is skipped and the weights are 0.50 / 0.40 / 0.10.
6. **Explain.** The top five are returned with matched and missing skills, a learning plan
   with links for each missing skill, certifications, salary range and growth outlook.

The weights are constants at the top of `backend/model.py`.

## The ML classifier

`backend/ml_model.py` adds a supervised model on top of the similarity engine.

- **Training data.** There is no labelled data of real people and the careers they chose, so
  training profiles are generated from `careers.csv`: 80 per career (12,800 in total). Each
  starts from one career's skills, drops a random share of them, adds some preferred skills
  and strengths, mixes in part of a second career for about a third of profiles (career
  changers), adds a few unrelated skills as noise, and varies education and experience.
- **Features.** One binary column per known skill or strength (about 720), plus education
  level and years of experience scaled to 0 to 1.
- **Model selection.** Logistic Regression, Random Forest and Bernoulli Naive Bayes are
  trained on an 80/20 stratified split. The one with the lowest log loss on the test set is
  kept, because the recommender uses the predicted probabilities, then refitted on all data.
- **Results on this dataset** (held-out generated profiles):

  | Algorithm | Accuracy | Top-3 accuracy | Macro F1 | Log loss |
  | --- | --- | --- | --- | --- |
  | Logistic Regression | 93.0% | 97.9% | 0.930 | 0.366 |
  | Random Forest | 87.9% | 96.8% | 0.879 | 0.938 |
  | Naive Bayes (Bernoulli) | 93.8% | 98.1% | 0.938 | 0.257 (selected) |

  These scores show how well the model learned the career dataset. The test profiles are
  generated the same way as the training profiles, so they are **not** a measure of how
  accurate the advice is for real people. Real feedback data would be needed for that.
- **Training happens automatically.** On first start, and whenever `careers.csv` or the
  installed scikit-learn version changes, the API trains the model (10 to 30 seconds, depending on the computer) and
  saves it to `backend/models/career_classifier.joblib`, with the metrics alongside in
  `career_classifier.metrics.json`. To retrain on demand and see the comparison table:

  ```bash
  cd backend
  python train_model.py
  ```

  On Windows, with the virtual environment not activated: `.venv\Scripts\python train_model.py`.
- `GET /api/model` returns the full training report.

## Data and limitations

- **The dataset is a mock.** Salary bands (Indian rupees per year, India-market) and ten-year growth percentages
  in `careers.csv` are illustrative estimates written for this demo. Replace them with a
  licensed or public source, such as national labour statistics, before showing them to real
  users.
- **Learning links.** About 90 skills have curated links to well-known free resources. Other
  skills fall back to a Coursera or edX search link, labelled "Search" in the interface.
- **Match scores are similarity scores,** not hiring predictions. They say how closely a
  profile resembles a career description.
- **Anonymous runs are stored too,** without an owner, unless the request sends
  `save_profile: false`. Add a retention policy before deploying publicly.
- **`python seed.py --reset` deletes accounts** and saved results along with the careers.
- Scanned (image-only) PDFs cannot be read; paste the text instead.

## The dataset

`backend/data/careers.csv` holds 160 careers across 28 fields: technology, data and AI,
healthcare, core engineering, finance and banking, law and government, education, media and
the arts, design, hospitality, aviation, science, agriculture, sports and more. Each row has
required and preferred skills, strengths and interests, the usual education and experience,
an India-market salary band in rupees, a ten-year growth estimate, certifications and a
description. The skill taxonomy built from it has about 720 entries.

The dataset was written for this project. Salaries and growth figures are illustrative
estimates. For real occupational data, O*NET (onetcenter.org, CC BY 4.0) publishes skills,
technologies and education requirements for about 900 occupations; mapping it to these
columns would need an import script, and Indian salary data would still have to come from
another source.

## Editing the dataset

Edit the definitions in `backend/data/build_dataset.py`, then:

```bash
cd backend
python data/build_dataset.py
python seed.py --reset
```

Restart the server so the embeddings are rebuilt. You can also edit `careers.csv` directly;
list values are separated by semicolons.
# AI-Career-Recommender
AI career recommender that matches a user’s skills, education and resume to 160 careers using TF-IDF/Sentence-BERT similarity and a Naive Bayes classifier, with skill-gap analysis, learning resources and salaries in INR. Built with React, FastAPI and scikit-learn.
