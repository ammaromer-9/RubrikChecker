# RubricCheck

A pre-submission grading assistant for students. Paste the assignment instructions, the rubric and a draft. RubricCheck predicts a score for every rubric criterion with a likely range, highlights the passages of the draft that justify each score, and gives feedback that helps the student improve **without writing or rewriting their work**.

- **Predicted score with an honest range**, e.g. "13/16, likely 5-16", from several independent grading runs, with criteria flagged *uncertain* when the runs disagree.
- **Evidence you can check:** every score cites quotes, and each quote is verified against the draft in code, so a made-up quote is never shown as evidence.
- **Feedback that coaches, not ghostwrites:** what is missing (in the rubric's own words), where, and guiding questions. A post-check blocks drafted text from reaching the student.
- **Revisions:** submit new versions and see what improved, what was fixed, and whether a change is bigger than the grader's own noise.
- **Calibration tooling** to measure how well the grader agrees with human graders, and to compare grading strategies and models.

## Screenshots

> Screenshot placeholders. Add the images listed in [docs/screenshots/README.md](docs/screenshots/README.md) and replace these lines with image links.
>
> - New assignment: `docs/screenshots/new-assignment.png`
> - Rubric review: `docs/screenshots/rubric-review.png`
> - Results with highlighted draft: `docs/screenshots/results.png`
> - Version comparison: `docs/screenshots/comparison.png`
> - Revision history and trend: `docs/screenshots/history.png`

## How it works

1. **New assignment:** paste or upload (PDF, .docx, .txt) the instructions and the rubric.
2. **Review the rubric:** the rubric is converted to structured criteria and levels by the LLM, then shown in an editable table. Levels the model had to invent are flagged *inferred*. **Grading only ever uses the version you confirm.**
3. **Submit a draft** and get results: score and range, instruction checklist, top 3 fixes, per-criterion cards, and the draft with evidence highlighted (green = meets, red = falls short; click either way to jump between draft and card).
4. **Submit a new version** and compare: per-criterion changes, issues you fixed, and a score trend.

## Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI["React + TypeScript SPA"]
  end
  subgraph API["FastAPI backend"]
    R["Routers"]
    RP["rubric_parser"]
    IC["instruction_checks<br/>deterministic, no LLM"]
    G["grader<br/>N runs per criterion"]
    EV["evidence verifier"]
    SC["scoring<br/>median, range, uncertain"]
    FB["feedback + no-rewrite check"]
    LC["LLM client<br/>retries, JSON parsing, call log"]
  end
  DB[("PostgreSQL")]
  LLM["Anthropic API"]

  UI -->|"JSON over /api"| R
  R --> RP
  R --> IC
  R --> G
  G --> EV
  G --> SC
  G --> FB
  RP --> LC
  G --> LC
  FB --> LC
  LC --> LLM
  LC -->|"llm_calls"| DB
  R --> DB
```

### What happens when you press "Check my draft"

```mermaid
sequenceDiagram
  participant U as Student
  participant A as API
  participant L as Anthropic
  participant D as Postgres
  U->>A: POST /submissions/{id}/grade
  A->>D: create grading (status running)
  A->>A: run instruction checks (plain Python)
  loop every criterion, N runs each, concurrent up to a limit
    A->>L: grade one criterion
    L-->>A: level, reasoning, quotes (JSON)
  end
  A->>A: verify quotes against the draft, take median and range
  loop each criterion that lost points
    A->>L: write feedback
    L-->>A: gaps and guiding questions
  end
  A->>A: reject drafted-looking text, else use a generic hint
  A->>D: save results (status complete)
  A-->>U: scores, evidence offsets, feedback
```

### Data model

```mermaid
erDiagram
  assignments ||--o{ submissions : "has versions"
  submissions ||--o{ gradings : "graded by"
  gradings ||--o{ criterion_results : has
  gradings ||--o{ instruction_check_results : has
  gradings |o--o{ llm_calls : "cost and latency"
  assignments {
    int id
    text instructions_text
    text rubric_raw_text
    jsonb rubric_parsed
    bool rubric_confirmed
    jsonb requirements_parsed
  }
  submissions {
    int id
    int version_number
    text draft_text
  }
  gradings {
    int id
    text strategy
    text model
    int num_runs
    float overall_median
    text status
    text prompt_version
  }
  criterion_results {
    text criterion_id
    float median_points
    bool uncertain
    jsonb evidence
    jsonb feedback
  }
```

### Project layout

```
backend/
  app/
    main.py, config.py, db.py, deps.py
    models/        SQLAlchemy models
    schemas/       Pydantic request, response and LLM-output schemas
    routers/       FastAPI routes
    services/      llm_client, rubric_parser, grader, scoring, evidence,
                   feedback, instruction_checks, comparison, file_extract
    prompts/       versioned prompt templates (name.vN.txt)
    eval/          calibration: datasets, metrics, strategies, runner, report
  alembic/         migrations
  scripts/         calibrate.py (CLI) and example data
  tests/
frontend/          React + Vite + Tailwind, typed API client
docs/              deployment notes, screenshot guide
docker-compose.yml PostgreSQL (and the API with --profile full)
```

## Getting started

Prerequisites: Python 3.11+, Node 20+, Docker.

```bash
# 1. Environment: copy, then set ANTHROPIC_API_KEY (the example file already sets a model)
cp .env.example .env

# 2. Database
docker compose up -d db

# 3. Backend (http://localhost:8000, interactive API docs at /docs)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# 4. Frontend (http://localhost:5173), in a second terminal
cd frontend
npm install
npm run dev
```

To run the API in a container instead of step 3:

```bash
docker compose --profile full run --rm api alembic upgrade head   # once
docker compose --profile full up -d api
```

## Configuration

Everything is configured with environment variables (12-factor); see `.env.example`. Invalid values stop the server at startup with a clear message.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local Postgres | `postgresql+asyncpg://user:pass@host:5432/db` |
| `ANTHROPIC_API_KEY` | none | Required for grading, rubric parsing and feedback |
| `ANTHROPIC_MODEL` | none | Model id, e.g. `claude-sonnet-5-5` |
| `ANTHROPIC_EFFORT` | `medium` | Thinking depth: `low`, `medium`, `high`, `xhigh`, `max` (empty = model default) |
| `GRADING_RUNS` | `3` | Independent runs per criterion (1-7) |
| `GRADING_CONCURRENCY` | `5` | Maximum simultaneous model calls per grading |
| `GRADING_STALE_MINUTES` | `30` | A grading still "running" this long after starting is marked failed at startup |
| `FEEDBACK_MAX_QUOTED_WORDS` | `25` | Longest non-student quote allowed in feedback |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `120` / `3` | Per-call timeout; retries with backoff on rate limits and 5xx |
| `MAX_DRAFT_CHARS` | `50000` | Longest accepted draft |
| `MAX_ASSIGNMENT_TEXT_CHARS` | `20000` | Longest accepted instructions or rubric |
| `MAX_UPLOAD_BYTES` | `5242880` | Largest uploaded file |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | Python log level |
| `VITE_API_BASE_URL` | empty | Frontend build setting, only if the API is on another origin |

## API

Interactive docs are served at `/docs`. All routes are under `/api`.

| Method and path | Purpose |
|---|---|
| `POST /files/extract` | Text from an uploaded PDF, .docx or .txt |
| `POST /assignments` | Create an assignment (instructions and raw rubric) |
| `GET /assignments/{id}` | Read it |
| `POST /assignments/{id}/parse-rubric` | LLM converts the rubric to criteria and levels |
| `PUT /assignments/{id}/rubric` | Save the user-edited rubric and mark it confirmed |
| `POST /assignments/{id}/extract-requirements` | Extract checkable requirements from the instructions |
| `POST /assignments/{id}/submissions` | Add a draft as the next version |
| `GET /submissions/{id}` | Read a draft |
| `POST /submissions/{id}/grade` | Grade it (synchronous), optional `{"num_runs": 1-7}` |
| `GET /gradings/{id}` | Full results |
| `GET /assignments/{id}/history` | All versions with scores, for trends |
| `GET /submissions/{id}/compare/{previous_id}` | What changed between two versions |
| `GET /health` | Liveness and database check |

Errors are JSON `{"detail": "..."}` with meaningful statuses: 404 unknown id, 409 rubric not confirmed or version not graded, 413 input too large, 422 invalid input, 502/503 when the AI service fails or is unavailable or not configured.

## How grading works

- **One model call per criterion**, repeated `GRADING_RUNS` times concurrently (under a limit). Each call sees only that criterion's level descriptions, reasons before choosing a level, and returns structured JSON.
- **Per criterion:** median points, the min-max range, and an **uncertain** flag when the runs differ by more than one rubric level (counted in levels, not points). The overall score is the sum of the medians. Its range sums the per-criterion minimums and maximums, which is deliberately conservative.
- **Points come from the confirmed rubric**, never from a number the model wrote: the model picks a level label (validated against the rubric) and the level's points are looked up.
- **Evidence is verified.** Each quote must be a verbatim substring of the draft (whitespace and curly-versus-straight quotes are ignored). Verified quotes are stored with character offsets for highlighting. Unverified ones are kept but flagged and never highlighted.
- **Instruction checks are plain Python.** The LLM is used once to turn the instructions into a list of checkable requirements (word count range, required headings, minimum citations, citation style). The checks themselves are deterministic code with no model involved.
- **Sampling:** current Claude models fix their sampling parameters, so `temperature` cannot be set. Runs differ through the model's default sampling, which is what makes the spread across runs meaningful.

## Design decisions

| Decision | Why |
|---|---|
| Confirm the rubric before grading | A misread rubric silently ruins every score. The user fixes it once, up front. |
| Grade each criterion separately | Keeps the model focused on one standard and makes disagreement visible per criterion. Compare against one-call grading with the calibration tool. |
| Report a range and an uncertain flag | A single number overstates precision. Disagreement between runs is the cheapest honest signal of grader uncertainty. |
| Verify quotes in code | Models sometimes invent evidence. The check turns "trust the model" into "show me the text". |
| Deterministic instruction checks | Word counts and headings are exact; asking a model to count words is slower, costlier and wrong. |
| Look up points from the rubric | The model cannot award points the rubric doesn't define. |
| Grading is synchronous but isolated | Simplest thing that works for an MVP, with `run_grading()` already separate so a queue and worker can replace the request later. |
| Prompts are versioned files | The prompt version is stored on every grading and model call, so results trace back to the exact wording. |
| Log every model call | `llm_calls` records tokens, latency and failures, so cost and reliability are queryable. |
| Mock the model in tests | Tests never call the real API; a fake provider plays the grader, feedback writer and parser. |
| Compare changes against grader noise | A version comparison says when a score change is inside the two versions' ranges and may not be real. |

## Academic-integrity design

The feedback exists to help students improve their own work, so it must never become a way to get text written for them. Two layers enforce that:

1. **Prompt:** the feedback prompt forbids rewritten sentences, sample paragraphs, model thesis statements and sample citations. It asks for the gap (in the rubric's wording) plus one or two guiding questions.
2. **Post-check:** model output is not trusted. Code scans every feedback field for long passages (more than `FEEDBACK_MAX_QUOTED_WORDS`, default 25 words) inside quotation marks, blockquotes or code fences that do **not** appear in the student's own draft. Flagged feedback is regenerated once; if it is still flagged, it is replaced by a generic hint built from the rubric's next-level description (marked as general guidance in the UI).

Why this shape: the failure that matters is the model "helpfully" drafting replacement text, and long fabricated quotations are how that shows up. The check is cheap, deterministic and fails safe. It is a heuristic, not a guarantee: it cannot detect every paraphrased suggestion, and quoting the student's own long passage back to them is allowed.

## Calibration

`backend/scripts/calibrate.py` measures how closely the grader agrees with human graders. Per strategy it reports mean absolute error (points and % of the scale), bias, **coverage** (how often the human score falls inside the predicted range, shown next to range width so a very wide range can't look good for free), quadratic weighted kappa, Pearson r, per-criterion agreement where per-criterion human scores exist, and the share of evidence quotes that really appear in the essay. It writes a markdown report.

**It calls the real API and costs money.** It prints the number of calls first and asks before spending anything (`--dry-run` stops there, `--yes` skips the question). Progress is saved as it goes, so an interrupted run continues with `--resume <run folder>`. Put datasets in `backend/data/` (gitignored; nothing is downloaded for you), and run from `backend/`:

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

Strategies: `per_criterion` (one call per criterion, as in the app) or `holistic` (one call grades every criterion), optionally `:no_evidence` (no supporting quotes requested) and `@<model>` to compare models, e.g. `per_criterion@claude-haiku-5-5`. A JSON file via `--config` works too. The rubric must be on the same scale as the human scores (ASAP rubric text should total the score range's maximum, e.g. 12 for set 1); predictions are clamped to what a human could have given; QWK is reported only when all essays share one integer scale.

### Calibration results

**Not yet measured.** No calibration run has been made, so this README reports no accuracy numbers and none should be assumed. After running the commands above, paste the strategy comparison table from `backend/reports/<run>/report.md` here, with the dataset, number of essays, number of runs, model and date.

| Strategy | Model | Essays | MAE (pts) | MAE (%) | Bias | Coverage | Range width | QWK | Quotes verified |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| per_criterion | | | | | | | | | |
| holistic | | | | | | | | | |
| per_criterion:no_evidence | | | | | | | | | |

## Testing

```bash
docker compose up -d db          # database tests need Postgres
cd backend && pytest             # applies the migrations to a separate test database
ruff check .
cd ../frontend && npm test       # Vitest + React Testing Library
npm run build                    # type-checks and builds
```

Backend tests cover rubric validation, evidence verification (including whitespace edge cases), instruction checks, score aggregation, the feedback no-rewrite check, file extraction, the API endpoints against a real test database, and the calibration tooling. The model is always mocked. One test file also stubs the Anthropic SDK client to pin down the exact arguments sent to the real SDK. Database tests are skipped, with a message, if Postgres isn't reachable.

## Deployment

The API ships as a container (`backend/Dockerfile`: non-root user, health check, migrations run as a separate step). See [docs/deployment-aws.md](docs/deployment-aws.md) for an AWS plan (ECS Fargate, RDS, S3 + CloudFront), including why grading time constrains the load-balancer setup and what to add before the site is public.

## Limitations

- **No accounts, no rate limiting.** Do not expose it publicly as-is: anyone could spend your API credits. See the deployment notes.
- **Accuracy has not been measured.** The score is a prediction, not a grade. Run the calibration before trusting it for anything that matters.
- **Grading is synchronous**, so a request can take minutes; a background worker is the planned next step.
- **Citation checks** count in-text patterns only (APA, Harvard, MLA, IEEE) and do not parse the reference list. Other styles are not checked.
- **A rubric edited after grading** changes the criterion names and maximums shown for old results (scores are kept).
- **The integrity check is a heuristic** and cannot catch every paraphrased suggestion.
- Student drafts are sent to the Anthropic API; check that this fits your data-protection requirements.
