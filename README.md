# RubricCheck

A pre-submission grading assistant for students. Paste the assignment instructions, the rubric and a draft. RubricCheck predicts a score per rubric criterion with a range, highlights the evidence in the draft, and gives feedback that helps you improve without writing the work for you.

> Status: Phase 7 (grading, frontend, revisions, calibration). Features land phase by phase.

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

## Calibration

`backend/scripts/calibrate.py` checks how closely the grader agrees with human graders. It reports, per strategy: mean absolute error (points and % of the scale), bias, how often the human score falls inside the predicted range (**coverage**, shown next to the range width so a very wide range can't look good for free), quadratic weighted kappa, Pearson r, per-criterion agreement where per-criterion human scores exist, and the share of evidence quotes that really appear in the essay. It writes a markdown report with a strategy comparison table.

**This calls the real API and costs money.** It prints the number of calls first and asks before spending anything (`--dry-run` stops there; `--yes` skips the question). Predictions are saved as it goes, so an interrupted run can continue with `--resume <run folder>`.

Datasets go in `backend/data/` (gitignored; nothing is downloaded for you). Run from `backend/`:

```bash
# Your own CSV: columns instructions, rubric (or rubric_json), draft, human_score,
# optional id, max_score and criterion_<id> per-criterion human scores.
# See scripts/examples/example_essays.csv.
python -m scripts.calibrate custom --data data/essays.csv --strategies per_criterion holistic

# ASAP-AES: the data file has no prompt or rubric text, so you provide them.
python -m scripts.calibrate asap --data data/training_set_rel3.tsv --essay-set 1 \
    --instructions-file data/set1_prompt.txt --rubric-file data/set1_rubric.txt \
    --limit 30 --seed 0 --strategies per_criterion per_criterion:no_evidence holistic
```

Strategies are `per_criterion` (one call per criterion, as in the app) or `holistic` (one call grades every criterion), optionally `:no_evidence` (the grader is not asked for supporting quotes) and `@<model>` to compare models, e.g. `per_criterion@claude-haiku-5-5`. A JSON file via `--config` works too. Reports land in `backend/reports/` (gitignored).

Notes: the rubric must be on the same scale as the human scores (ASAP rubric text should total the score range's maximum, e.g. 12 for set 1); predicted scores are clamped to the range a human could have given; QWK is only reported when all essays share one integer scale.

## Tests

Database tests need Postgres running (`docker compose up -d db`); they apply the Alembic migrations to the `rubriccheck_test` database and are skipped if it is unreachable. The LLM is always mocked.

```bash
cd backend && pytest
```

## Configuration

All config is via environment variables (see `.env.example`), following 12-factor.
