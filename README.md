# RubricCheck

A pre-submission grading assistant for students. Paste the assignment instructions, the rubric and a draft. RubricCheck predicts a score per rubric criterion with a range, highlights the evidence in the draft, and gives feedback that helps you improve without writing the work for you.

> Status: Phase 2 (database, LLM client, file extraction). Features land phase by phase.

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


## Tests

Database tests need Postgres running (`docker compose up -d db`); they apply the Alembic migrations to the `rubriccheck_test` database and are skipped if it is unreachable. The LLM is always mocked.

```bash
cd backend && pytest
```

## Configuration

All config is via environment variables (see `.env.example`), following 12-factor.
