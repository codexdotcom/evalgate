from __future__ import annotations
import asyncio, json, statistics, time

from anthropic import AsyncAnthropic

from .scorers import ScoreResult
from .ratelimit import call_model

client = AsyncAnthropic()

PROMPT = """You are grading an AI agent's trajectory against a rubric.

<rubric>{rubric}</rubric>
<task>{prompt}</task>
<trajectory>{traj}</trajectory>

Respond with ONLY this JSON, no prose, no markdown fences:
{{"passed": true|false, "reason": "<one sentence>"}}"""

# Per-token pricing, (input, output).
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0 / 1e6, 15.0 / 1e6),
    "claude-haiku-4-5": (1.0 / 1e6, 5.0 / 1e6),
}

MAX_CONTENT_CHARS = 1500
MAX_TRAJ_CHARS = 20000


def _strip_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[1] if "\n" in text else ""
    return body.rsplit("```", 1)[0].strip()


class LLMJudge:
    """Rubric judge with self-consistency.

    Confidence is derived from vote spread across independent samples, not
    from asking the model to rate itself. A 3/3 split is 1.0, a 2/1 is 0.33.
    That number is measurable against human labels, which is the point.
    """

    key, kind = "rubric_judge", "llm_judge"

    def __init__(self, model: str = "claude-sonnet-4-6", samples: int = 3) -> None:
        self.model = model
        self.samples = samples

    async def _vote(self, body: str) -> tuple[dict, object]:
        # Retry, backoff and the shared 429 gate all live in call_model, so
        # every model caller in the worker throttles against one clock.
        r = await call_model(
            client.messages.create,
            model=self.model,
            max_tokens=256,
            temperature=1.0,
            messages=[{"role": "user", "content": body}],
        )
        text = _strip_fences(r.content[0].text)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # An unparseable judge response is a failed vote, not a crashed
            # trajectory. Abstain rather than poison the sample.
            return {"passed": None, "reason": "unparseable judge output"}, r.usage

        if not isinstance(parsed, dict) or not isinstance(parsed.get("passed"), bool):
            return {"passed": None, "reason": "judge returned unexpected shape"}, r.usage
        return parsed, r.usage

    async def score(self, traj: dict, case: dict) -> ScoreResult:
        t0 = time.perf_counter()

        compact = [
            {
                "role": s["role"],
                "content": (s.get("content") or "")[:MAX_CONTENT_CHARS],
                "tools": [tc["name"] for tc in s.get("tool_calls", [])],
                "result": (s.get("tool_result") or "")[:400] if s.get("tool_result") else None,
            }
            for s in traj["steps"]
        ]
        body = PROMPT.format(
            rubric=case.get("rubric") or "The agent completed the task correctly.",
            prompt=case["prompt"],
            traj=json.dumps(compact)[:MAX_TRAJ_CHARS],
        )

        raw = await asyncio.gather(
            *(self._vote(body) for _ in range(self.samples)),
            return_exceptions=True,
        )

        votes: list[int] = []
        reasons: list[str] = []
        cost = 0.0
        cin, cout = PRICING.get(self.model, (3.0 / 1e6, 15.0 / 1e6))
        errors = 0

        for item in raw:
            if isinstance(item, BaseException):
                errors += 1
                continue
            parsed, usage = item
            cost += usage.input_tokens * cin + usage.output_tokens * cout
            if parsed.get("passed") is None:
                continue
            votes.append(int(parsed["passed"]))
            if parsed.get("reason"):
                reasons.append(str(parsed["reason"]))

        latency = int((time.perf_counter() - t0) * 1000)

        if not votes:
            # Zero usable votes. Fail closed with zero confidence so the
            # trajectory routes to human review rather than silently passing.
            note = f"no usable judge votes ({errors} errors of {self.samples})"
            return ScoreResult(self.key, self.kind, 0.0, False, 0.0, note, cost, latency)

        mean = statistics.mean(votes)
        confidence = abs(mean - 0.5) * 2
        passed = mean > 0.5

        rationale = next(
            (r for r, v in zip(reasons, votes) if bool(v) == passed),
            reasons[0] if reasons else None,
        )
        if len(votes) < self.samples:
            rationale = f"[{len(votes)}/{self.samples} votes usable] {rationale or ''}".strip()

        return ScoreResult(
            self.key, self.kind, mean, passed, confidence, rationale, cost, latency
        )