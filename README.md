# EvalGate

**An evaluation harness for LLM agents that measures how much you can trust its own scorers.**

Most agent eval stacks report a pass rate and stop there. That number is only
as good as the grader behind it, and an LLM judge that quietly passes broken
trajectories produces a green dashboard over a regressing agent.

EvalGate treats the scorer as the thing under test. Every run produces pass
rates *and* a Cohen's kappa against blind human labels, per scorer, with the
false-pass and false-fail counts that kappa hides. A judge below 0.6 kappa is
reported as untrustworthy and should gate nothing.

```
                    ┌──────────────────────────────────────────┐
                    │  React + Redux Toolkit Query (Vite)      │
                    │  runs · run detail · blind review queue  │
                    └───────────────────┬──────────────────────┘
                                        │ GraphQL
                    ┌───────────────────┴──────────────────────┐
                    │  GraphQL Yoga + Pothos (code-first)      │
                    │  Prisma 7 · pg driver adapter            │
                    └───────────────────┬──────────────────────┘
                                        │
                    ┌───────────────────┴──────────────────────┐
                    │              PostgreSQL 16               │
                    │  system of record AND the work queue     │
                    └───────────────────┬──────────────────────┘
                                        │ FOR UPDATE SKIP LOCKED
             ┌──────────────────┬───────┴───────┬──────────────────┐
             │   worker (py)    │   worker      │   worker  ... N  │
             │  execute → score → persist → flag for review        │
             └────────────────────────────────────────────────────┘
```

---

## Why this exists

Three failure modes kill agent evaluation in practice, and each one gets a
first-class answer here:

| Failure mode | What EvalGate does about it |
|---|---|
| **The judge is wrong and nobody checks.** Pass rates drift because the grader drifts. | Every scorer is scored. Blind human labels → Cohen's kappa, agreement, false pass, false fail — per scorer, per run. |
| **Human review is biased by the machine.** Showing a reviewer the judge's verdict makes them agree with it, and the resulting kappa is worthless. | Blind mode hides every scorer verdict until the reviewer commits. Calibration can be recomputed over blind labels only. |
| **Re-running evals costs real money**, so nobody runs them on every change. | Replay mode scores recorded trajectories without re-running the agent. Mock mode exercises the full pipeline against synthetic trajectories. |

---

## Engineering notes

The parts worth reading, and why they are built the way they are.

### Postgres as the queue, no broker

Workers claim work with `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP
LOCKED)`. Each worker's select steps over rows another worker already locked
instead of blocking on them, so N workers pull disjoint batches with no
coordinator, no broker, and no separate durability story. Enqueueing a run *is*
inserting its `Trajectory` rows.

The claim protocol has two halves. The reaper is the other one: a worker killed
mid-batch leaves rows pinned in `RUNNING` forever, so a background pass returns
anything stale past `STALE_AFTER` to `QUEUED`, bounded by `MAX_ATTEMPTS` so a
poison case cannot loop. `SIGTERM` stops new claims and drains in-flight work
rather than dropping it — paired with a `preStop` sleep and a 60s grace period
in the Kubernetes manifest, rolling a deployment loses nothing.

### Confidence that means something

The rubric judge samples the model three times at temperature 1.0 and derives
confidence from **vote spread**, not from asking the model to rate itself:
3/3 is `1.0`, 2/1 is `0.33`. That number is measurable against human labels,
which is the entire point — a self-reported confidence score is not.

Failure is handled as abstention, not as a crash. An unparseable judge response
is a failed vote, and a trajectory with zero usable votes fails closed at
confidence `0.0` so it routes to a human instead of silently passing.

### The review queue is populated by disagreement

Human attention is the scarcest input, so it is spent where the signal is.
After scoring, a trajectory is flagged when scorers disagree with each other
(`SCORER_DISAGREEMENT`) or when any scorer falls below `CONFIDENCE_FLOOR`
(`LOW_CONFIDENCE`). Passing trajectories can also be sampled in (`SAMPLED`) —
without them, kappa is computed over a biased slice.

### One rate-limit clock per process

A 429 from one coroutine closes a **process-wide gate**: every other model call
in that worker waits out the window instead of stampeding into the same limit.
Backoff honours `retry-after` where the provider sends it and applies full
jitter otherwise. The classification matters — 429/529 gate and retry, 5xx and
timeouts retry without gating (not a quota problem), and 4xx raises immediately
because retrying a malformed request only burns budget.

### Contracts generated, not hand-synced

The trajectory and score shapes are defined once in Zod
(`packages/contracts`), emitted to JSON Schema, and code-generated into
Pydantic models for the Python runner. The TypeScript API and the Python worker
cannot drift apart without the build noticing.

### Tolerant at the boundary, strict inside

`normalize_trajectory` accepts recorded trajectories in whatever shape they
arrive in — `tool_calls` or `toolCalls`, args as an object or a JSON string,
`messages` or `steps` — and returns exactly one canonical shape. Ingestion is
all-or-nothing and reports every malformed line at once, because a
half-ingested suite silently evaluates the wrong N. Re-ingesting the same file
is idempotent by `(suiteId, externalId)`, so you can fix a rubric and reload
without duplicating cases.

---

## Quick start

Requires Docker, Node 22 + pnpm, and Python 3.12 + [uv](https://docs.astral.sh/uv/).

```bash
# 1. Postgres
docker compose -f infra/docker-compose.yml up -d postgres
export DATABASE_URL=postgresql://evalgate:evalgate@localhost:5432/evalgate

# 2. Schema + API  (http://localhost:4000/graphql)
pnpm install
cd apps/api && pnpm exec prisma generate && pnpm exec prisma migrate deploy
pnpm exec tsx src/server.ts

# 3. Worker
cd apps/runner && uv sync && uv run python -m evalgate.worker

# 4. UI  (http://localhost:5173)
cd apps/web && pnpm dev
```

Load a suite and start a run:

```bash
cd apps/runner
uv run evalgate-ingest cases.jsonl --slug demo --dry-run   # parse, report, write nothing
uv run evalgate-ingest cases.jsonl --slug demo
```

```graphql
mutation { startRun(suiteSlug: "demo", model: "mock-model") { id totalCases } }
```

`mock-model` exercises the full pipeline — claim, score, persist, flag,
calibrate — against synthetic trajectories. Replay mode does the same for
recorded trajectories. Both are fully offline: the rubric judge is registered
only when `JUDGE_MODEL` is set, so an unconfigured worker scores
deterministically and makes no provider calls at all.

A live run needs three things — `ANTHROPIC_API_KEY`, a `JUDGE_MODEL`, and a
model id passed to `startRun`. Cost reporting additionally needs
`MODEL_PRICING`; without it a run still completes and simply reports zero
spend.

### Input format

One JSON object per line. Everything but `prompt` is optional.

```jsonc
{
  "id": "case-001",
  "prompt": "Find the bug in utils.py and fix it.",
  "rubric": "The agent located the defect and made a targeted fix.",
  "tags": ["python", "debugging"],
  "expected": { "final_output": "...", "tool_sequence": ["search", "read_file", "finish"] },
  "trajectory": { "steps": [] },              // present → replay, zero model calls
  "ground_truth": { "resolved": true }        // objective anchor, never a scorer input
}
```

A SWE-bench converter ships in the box. It pulls recorded agent trajectories
with execution-verified outcomes, balanced near 50/50 so kappa stays
meaningful — an eval set that is 95% failures makes any judge look calibrated.

```bash
uv pip install datasets
uv run evalgate-convert-swebench --n 200 --balance 0.45 --out datasets/swebench-200.jsonl
```

---

## Scorers

Every scorer returns the same `ScoreResult`, so adding one is a class with a
`score()` coroutine registered in `worker.SCORERS`.

| Key | Kind | Signal |
|---|---|---|
| `exact_match` | deterministic | Final output matches expected exactly. |
| `tool_sequence` | deterministic | Longest common subsequence against the expected tool order — partial credit, not a boolean. |
| `no_loops` | programmatic | Flags ≥3 identical consecutive tool calls, the classic agent failure. |
| `step_budget` | deterministic | Episode stayed within the step cap. |
| `rubric_judge` | llm_judge | 3-sample self-consistency vote against the case rubric. Registered only when `JUDGE_MODEL` is set. |

## Reading the calibration table

Per scorer, per run, over human-labelled trajectories:

| Kappa | Verdict | Meaning |
|---|---|---|
| ≥ 0.80 | **Strong** | Safe to gate on. |
| ≥ 0.60 | **Usable** | Trend-worthy, verify before acting. |
| ≥ 0.40 | **Weak** | Directional only. |
| < 0.40 | **Do not trust** | Agreement is chance. Fix the rubric. |

Kappa is used rather than raw agreement because agreement flatters a lazy
judge: one that passes everything against a suite that is 80% passing scores
80% and has learned nothing. Kappa corrects for that and goes negative when a
scorer is worse than a coin flip.

**False passes are the expensive error** — the judge cleared a trajectory a
human rejected — so they are broken out separately rather than folded into an
agreement percentage.

### The review UI

Keyboard-driven, because throughput is the constraint: `p` pass, `f` fail,
`u` undo, `b` toggle blind. The queue prefetches before the buffer runs dry and
deliberately does **not** invalidate its cache on every label — refetching
after each keystroke would reshuffle rows under the reviewer's cursor. Run
progress updates by polling, and the session tracks a labels-per-minute rate.

---

## Layout

```
apps/
  api/        GraphQL Yoga + Pothos, Prisma 7 schema and migrations
  runner/     Python workers: execute · score · judge · calibrate · ingest
  web/        React 19 + RTK Query review and analytics UI
packages/
  contracts/  Zod schemas → JSON Schema → Pydantic models
infra/        docker-compose (local) · Kubernetes worker Deployment
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Postgres DSN. Required everywhere. |
| `ANTHROPIC_API_KEY` | — | Required for live runs only. |
| `CONCURRENCY` | `8` | In-flight trajectories per worker. |
| `BATCH` | `16` | Rows claimed per poll. |
| `MAX_ATTEMPTS` | `3` | Retries before a trajectory is marked `FAILED`. |
| `STALE_AFTER` | `10 minutes` | Age at which the reaper requeues a stuck `RUNNING` row. |
| `CONFIDENCE_FLOOR` | `0.67` | Below this, a trajectory is routed to human review. |
| `JUDGE_MODEL` | unset | Model backing the rubric judge. Unset disables the judge entirely. |
| `MODEL_PRICING` | `{}` | JSON of `{"model-id": [input, output]}` per-token rates. Unpriced models cost zero. |
| `MAX_STEPS` | `20` | Agent step cap per episode. |
| `MODEL_MAX_RETRIES` | `6` | Retry budget per model call. |
| `MODEL_BASE_DELAY` / `MODEL_MAX_DELAY` | `1.0` / `60.0` | Backoff bounds in seconds. |

## Testing

```bash
cd apps/runner && uv run pytest -q     # scorer + kappa unit tests
cd apps/api    && pnpm exec tsc --noEmit
cd apps/web    && pnpm build
```

CI runs all three on every pull request against a real Postgres 16 service
container, with migrations applied — not a mock.

### Load testing

```bash
cd apps/runner && N_CASES=10000 uv run python -m evalgate.loadtest
```

Seeds a synthetic suite, enqueues it, and reports throughput plus p50/p95/p99
latency. It runs against `mock-model` on purpose: the goal is to measure
*harness* capacity — claim contention, transaction cost, connection pool
behaviour — without the measurement being swamped by provider latency.

## Scaling

Workers are stateless and coordinate only through Postgres, so capacity scales
by replica count. `infra/k8s/worker.yaml` runs three by default with a
drain-safe shutdown path.

## Not built yet

Stated plainly, because a roadmap presented as shipped features is worse than
no roadmap:

- **Auth.** The API is unauthenticated and assumes a trusted network.
- **Real tool sandbox.** The live agent loop ships stub tools; wire the registry
  in `execute.py` to a sandbox before drawing conclusions from live runs.
- **Inter-annotator agreement.** Kappa currently measures judge-vs-human. A
  second human pass would bound how much of the residual disagreement is the
  judge and how much is the rubric.
- **Cost budgets.** Spend is recorded per trajectory and per run but does not
  yet halt a run.
- **Per-run scorer selection.** The scorer list is fixed at
  `worker.SCORERS`; choosing scorers per suite or per run is config that
  belongs in the `Run` record.
