# RubricCheck

A pre-submission grading assistant for students. Paste the assignment instructions, the rubric and a draft. RubricCheck predicts a score per rubric criterion with a range, highlights the evidence in the draft, and gives feedback that helps you improve without writing the work for you.

> Status: Phase 6 (grading, frontend, revisions). Features land phase by phase.

## Stack

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, PostgreSQL, Pydantic v2
- LLM: Anthropic API via the official SDK
- Frontend: React, TypeScript, Vite, Tailwind CSS

## Setup

Prerequisites: Python 3.11+, Node 20+, Docker.

```bash
# 1. Environment
cp .env.example .env        # then fill in ANTHROPIC_API_KEY and ANTHROPIC_MODEL

# 2. Database
docker compose up -d db

# 3. Backend (http://localhost:8000, docs at /docs)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head        # create the database tables
uvicorn app.main:app --reload

# 4. Frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```


## How grading works

- Each rubric criterion is graded by its own LLM call, repeated `GRADING_RUNS` times (default 3). Current Claude models fix their sampling parameters (`temperature` can't be set), so the runs differ through the model's default sampling. Per criterion the app reports the median points, the min-max range, and flags it **uncertain** when runs disagree by more than one rubric level.
- The overall score is the sum of the medians. Its range sums the per-criterion minimums and maximums, which is deliberately conservative.
- The model must justify its score with quotes. Every quote is checked in code against the draft (ignoring whitespace and curly-vs-straight quotes) and stored with character offsets. Quotes that are not really in the draft are flagged as unverified, never highlighted.
- Points always come from the confirmed rubric level the model picked, not from a number the model wrote.

### Academic-integrity design

The feedback is meant to help students improve their own work, so it must never become a way to get text written for them. Two layers enforce that:

1. **Prompt:** the feedback prompt forbids rewritten sentences, sample paragraphs, model thesis statements, and sample citations. It asks for the gap (in the rubric's wording) plus one or two guiding questions.
2. **Post-check:** model output is not trusted. Code scans every feedback field for long passages (more than `FEEDBACK_MAX_QUOTED_WORDS`, default 25 words) inside quotation marks, blockquotes or code fences that do **not** appear in the student's own draft. Flagged feedback is regenerated once; if it is still flagged, it is replaced by a generic hint built from the rubric's next-level description.

This is a heuristic, not a guarantee. It catches the common failure (the model "helpfully" drafting a replacement passage) and fails safe, but it cannot detect every paraphrased suggestion.

## Tests

Database tests need Postgres running (`docker compose up -d db`); they apply the Alembic migrations to the `rubriccheck_test` database and are skipped if it is unreachable. The LLM is always mocked.

```bash
cd backend && pytest
```

## Configuration

All config is via environment variables (see `.env.example`), following 12-factor.
