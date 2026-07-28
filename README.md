# EvalGate

An LLM evaluation and governance harness. It runs a model against a dataset of
expected outputs, scores each case, **escalates the judgments it isn't confident
about to a human queue instead of guessing**, and freezes the outcome into a
hash-stamped pass/fail report.

The last two parts are the point. Plenty of tools will give you a pass rate.
An eval that quietly scores its own uncertain cases produces a number nobody
should act on — and a number nobody can audit later is not evidence of anything.

---

## The gate

Every case ends in one of three states, and the third is what makes this useful:

| Verdict | When |
| --- | --- |
| `pass` | Judge was confident, and the score cleared `PASS_THRESHOLD`. |
| `fail` | Judge was confident, and the score did not. |
| `needs_review` | Judge's confidence fell below the run's threshold — or the case errored outright. |

A run is then certified, or it isn't:

| Gate | Meaning |
| --- | --- |
| `pass` | Pass rate cleared `GATE_PASS_RATE` and nothing is waiting on a human. |
| `fail` | Pass rate fell short. |
| `blocked` | At least one case is still unresolved. **A blocked run cannot be certified at any pass rate.** |

An unresolved case is the system saying it could not decide. Averaging that into
a pass rate would launder the uncertainty into a number that looks like a
decision, so it doesn't get a vote — it blocks.

Two deliberate consequences:

- **Errors escalate, they don't fail.** A rate-limit or a malformed judge
  response means we never learned whether the model was right. Recording that as
  `fail` would be a verdict we didn't earn, so it goes to the queue.
- **Deterministic scorers never escalate.** `exact_match` reports confidence 1.0
  by construction, so gating it on a confidence threshold would be theatre.

## Pipeline

```
dataset case ──▶ model under test ──▶ scorer ──▶ confidence ≥ threshold?
                 (DEFAULT_MODEL)                  │
                                          yes ────┤──── no
                                                  │      │
                                       score ≥ PASS?     └──▶ review queue
                                          │                        │
                                    pass ──┴── fail          human verdict
                                          │                        │
                                          └────────┬───────────────┘
                                                   ▼
                                         report + SHA-256 gate
```

Cases fan out concurrently (`MAX_CONCURRENCY`, default 5) since each one costs
two API calls — the model's answer and the judge's grade.

## Example

A real run over `backend/sample_dataset.json`, at a deliberately strict
confidence threshold of 0.95:

```
verdict       score  conf  input
pass           1.00  0.99  What is the capital of France?
needs_review   0.95  0.92  Summarize the plot of a good movie in one sentence.
needs_review   0.20  0.85  Is a hot dog a sandwich? Answer yes or no.
pass           1.00  0.99  Name the largest planet in our solar system.
pass           1.00  1.00  What is 17 multiplied by 3?

gate before review: blocked   (needs_review=2)
gate after 2 human resolutions: pass
  {"total":5,"pass":5,"fail":0,"needs_review":0,"pass_rate":1.0,
   "decided_pass_rate":1.0,"human_reviewed":2,"gate":"pass"}
```

Note the two ambiguous cases: the judge was 85–92% confident, which most
harnesses would treat as confident enough. At a 0.95 bar they route to a human,
and the run is *blocked* until someone rules — then certified, with
`human_reviewed: 2` recorded in the report.

## Reports are reproducible

`content_hash` is a SHA-256 over a canonical payload of every case's verdict,
score, and confidence. Regenerating a report over unchanged results reproduces
the digest exactly; if a verdict moves, the digest moves.

The payload is ordered by `case_id`, not by insertion order — every result in a
run is written in one transaction and therefore shares a `created_at`, so
Postgres is free to return them in any order it likes. Ordering the payload by
timestamp would make the hash wobble between generations and "the hash changed"
would stop meaning anything.

---

## Stack

- **Backend** — Python 3.13, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, pytest
- **Database** — PostgreSQL (developed against [Neon](https://neon.tech); any Postgres works, and SQLite for tests)
- **LLM** — Anthropic API (`claude-haiku-4-5` under test, `claude-sonnet-5` as judge, both configurable)
- **Frontend** — Next.js 16 (App Router), React 19, TypeScript, Tailwind v4

## Quickstart

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements-dev.txt

cp .env.example .env      # then fill in DATABASE_URL and ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Tables are created on startup. API docs at http://127.0.0.1:8000/docs.

No Postgres handy? Set `DATABASE_URL=sqlite+aiosqlite:///./evalgate.db` and it
runs with no server at all. `docker-compose.yml` provisions a local Postgres if
you'd rather have one.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                        # http://localhost:3000
```

Reads happen in server components and mutations go through server actions, so
the browser never calls FastAPI directly — there's no CORS to configure and no
API key exposed to the client.

### Configuration

All backend settings live in `backend/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local Postgres | Neon/Postgres/SQLite connection string |
| `ANTHROPIC_API_KEY` | — | Required for `llm_judge` runs |
| `DEFAULT_MODEL` | `claude-haiku-4-5-20251001` | Model being evaluated |
| `JUDGE_MODEL` | `claude-sonnet-5` | Model doing the grading |
| `DEFAULT_CONFIDENCE_THRESHOLD` | `0.75` | Below this, escalate to a human |
| `PASS_THRESHOLD` | `0.7` | Score at or above this passes |
| `GATE_PASS_RATE` | `0.9` | Share of cases that must pass to certify |
| `MAX_CONCURRENCY` | `5` | Cases evaluated in parallel |

#### A note on Neon

The connection string Neon hands you does not work with asyncpg as-is, so
`app/database.py` normalizes it: `sslmode` and `channel_binding` are lifted out
of the URL into `connect_args` (SQLAlchemy would otherwise forward them to
`asyncpg.connect()`, which rejects them), and `postgresql://` is upgraded to
`postgresql+asyncpg://`.

If you use the **pooled** (`-pooler`) endpoint, that's PgBouncer in transaction
mode: prepared statements created on one backend are missing on the next. Both
statement caches are disabled and prepared-statement names are made unique, or
you get intermittent `InvalidSQLStatementNameError`. Paste either endpoint and
it will work.

## API

| Method | Path | |
| --- | --- | --- |
| `POST` | `/datasets` | Create a dataset with its cases |
| `GET` | `/datasets` | List datasets with case counts |
| `GET` | `/datasets/{id}` | Dataset with all cases |
| `POST` | `/runs` | Start a run (executes in the background) |
| `GET` | `/runs` | List runs |
| `GET` | `/runs/{id}` | Run status |
| `GET` | `/runs/{id}/results` | Per-case results |
| `POST` | `/runs/{id}/report` | Freeze a report (completed runs only) |
| `GET` | `/runs/{id}/report` | Latest report |
| `GET` | `/review?status=pending\|all` | Review queue, with case context inlined |
| `POST` | `/review/{id}/resolve` | Record a human verdict |

Resolving a review item overwrites the machine verdict and **appends** to the
result's reasoning rather than replacing it, so the judge's original rationale
and the human's override both survive. Items can only be resolved once.

```bash
curl -X POST localhost:8000/datasets -H 'content-type: application/json' \
     -d @backend/sample_dataset.json

curl -X POST localhost:8000/runs -H 'content-type: application/json' \
     -d '{"dataset_id":"<id>","scorer":"llm_judge","confidence_threshold":0.95}'
```

## Tests

```bash
cd backend && python -m pytest        # 51 tests, ~2s, no network, no database server
```

The suite runs against in-memory SQLite with a fake LLM, so it needs neither an
API key nor Neon. It covers the routing rules (low confidence escalates, errors
escalate, deterministic scorers don't), the gate semantics, hash reproducibility,
per-case failure isolation, and the Neon URL normalization above.

## Layout

```
backend/
  app/
    routers/     datasets, runs, review, reports
    scorers/     exact_match, llm_judge  (add one by subclassing Scorer)
    services/    runner, report, llm_client
    models.py    Dataset, EvalCase, EvalRun, EvalResult, ReviewItem, Report
  tests/
frontend/
  app/           runs, runs/[id], review, datasets
  lib/           api client, server actions
```

Adding a scorer means subclassing `Scorer`, returning a `ScoreResult`
(score, confidence, reasoning), and registering it in `scorers/__init__.py`.
Set `deterministic = True` if its confidence is not meaningful.

## Known gaps

Honest about what this is and isn't:

- Runs execute in a FastAPI `BackgroundTask`, so a restart mid-run leaves the
  run stuck in `running`. A real deployment wants a task queue.
- No authentication — the review queue trusts whatever name it's given.
- Schema is created with `create_all` on startup rather than migrations.
