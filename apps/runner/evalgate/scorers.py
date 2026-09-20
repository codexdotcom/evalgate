from __future__ import annotations
import json, re, time
from dataclasses import dataclass
from typing import Protocol, Any

@dataclass(slots=True)
class ScoreResult:
    scorer_key: str
    scorer_kind: str
    value: float
    passed: bool
    confidence: float
    rationale: str | None = None
    cost_usd: float = 0.0
    latency_ms: int = 0

class Scorer(Protocol):
    key: str
    kind: str
    async def score(self, traj: dict[str, Any], case: dict[str, Any]) -> ScoreResult: ...


class ExactMatch:
    key, kind = "exact_match", "deterministic"
    async def score(self, traj, case):
        expected = (case.get("expected") or {}).get("final_output", "")
        ok = traj["final_output"].strip() == str(expected).strip()
        return ScoreResult(self.key, self.kind, float(ok), ok, 1.0)


class ToolCallSequence:
    """Did the agent call the right tools in the right order? The single most
    useful deterministic signal for agent evals."""
    key, kind = "tool_sequence", "deterministic"

    async def score(self, traj, case):
        expected = (case.get("expected") or {}).get("tool_sequence")
        if not expected:
            return ScoreResult(self.key, self.kind, 1.0, True, 0.0, "no expectation")
        actual = [tc["name"] for s in traj["steps"] for tc in s.get("tool_calls", [])]
        lcs = _lcs_len(expected, actual)
        value = lcs / max(len(expected), 1)
        return ScoreResult(
            self.key, self.kind, value, value == 1.0, 1.0,
            f"expected={expected} actual={actual}",
        )


class NoLoops:
    """Agents fail by looping. Flag >=3 identical consecutive tool calls."""
    key, kind = "no_loops", "programmatic"

    async def score(self, traj, case):
        sig = [
            json.dumps({"n": tc["name"], "a": tc["args"]}, sort_keys=True)
            for s in traj["steps"] for tc in s.get("tool_calls", [])
        ]
        worst, run, prev = 1, 1, None
        for x in sig:
            run = run + 1 if x == prev else 1
            worst, prev = max(worst, run), x
        ok = worst < 3
        return ScoreResult(self.key, self.kind, float(ok), ok, 1.0, f"max_repeat={worst}")


class StepBudget:
    key, kind = "step_budget", "deterministic"
    def __init__(self, max_steps: int = 20): self.max_steps = max_steps
    async def score(self, traj, case):
        n = len(traj["steps"])
        ok = n <= self.max_steps
        return ScoreResult(self.key, self.kind, float(ok), ok, 1.0, f"steps={n}")


def _lcs_len(a: list[str], b: list[str]) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            dp[i][j] = dp[i-1][j-1] + 1 if x == y else max(dp[i-1][j], dp[i][j-1])
    return dp[-1][-1]