from app.scorers.base import ScoreResult, Scorer


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


class ExactMatchScorer(Scorer):
    name = "exact_match"
    deterministic = True

    async def score(self, *, input: str, expected: str, actual: str) -> ScoreResult:
        match = _norm(expected) == _norm(actual)
        return ScoreResult(
            score=1.0 if match else 0.0,
            confidence=1.0,  # deterministic → never routed to review
            reasoning=(
                "Exact normalized string match"
                if match
                else "Outputs differ after normalization"
            ),
        )