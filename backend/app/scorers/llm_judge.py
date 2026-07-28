import json

from app.config import settings
from app.scorers.base import ScoreResult, Scorer
from app.services import llm_client

JUDGE_SYSTEM = "You are a strict, fair evaluation judge. Output only valid JSON."

JUDGE_INSTRUCTIONS = (
    "Compare the ACTUAL output against the EXPECTED output for the given INPUT.\n"
    "Return ONLY a JSON object (no prose, no markdown) with keys:\n"
    '  "score": float 0..1 — how correct/complete ACTUAL is vs EXPECTED '
    "(1 = fully correct).\n"
    '  "confidence": float 0..1 — how confident you are in THIS judgment. '
    "Be low when the case is ambiguous, EXPECTED is underspecified, or several "
    "answers could be valid.\n"
    '  "reasoning": a short string explaining the score and confidence.'
)


def _parse_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1:
        t = t[start : end + 1]
    return json.loads(t)


class LLMJudgeScorer(Scorer):
    name = "llm_judge"

    def __init__(self, model: str | None = None):
        self.model = model or settings.judge_model

    async def score(self, *, input: str, expected: str, actual: str) -> ScoreResult:
        prompt = (
            f"{JUDGE_INSTRUCTIONS}\n\n"
            f"INPUT:\n{input}\n\n"
            f"EXPECTED:\n{expected}\n\n"
            f"ACTUAL:\n{actual}\n\n"
            "JSON:"
        )
        raw = await llm_client.complete(
            self.model, prompt, system=JUDGE_SYSTEM, max_tokens=500
        )
        data = _parse_json(raw)
        return ScoreResult(
            score=float(data["score"]),
            confidence=float(data["confidence"]),
            reasoning=data.get("reasoning"),
        )