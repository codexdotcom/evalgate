from dataclasses import dataclass
from typing import Optional


@dataclass
class ScoreResult:
    score: float          # 0..1 correctness
    confidence: float     # 0..1 judge certainty
    reasoning: Optional[str]


class Scorer:
    name: str = "base"

    # Deterministic scorers report confidence 1.0 by construction, so gating
    # them on the confidence threshold is meaningless — the runner skips the
    # review routing for them entirely.
    deterministic: bool = False

    async def score(self, *, input: str, expected: str, actual: str) -> ScoreResult:
        raise NotImplementedError