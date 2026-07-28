import pytest

from app.scorers import get_scorer
from app.scorers.exact_match import ExactMatchScorer
from app.scorers.llm_judge import LLMJudgeScorer, _parse_json


async def test_exact_match_ignores_case_and_whitespace():
    result = await ExactMatchScorer().score(
        input="capital of France?", expected="Paris", actual="  paris \n"
    )
    assert result.score == 1.0
    assert result.confidence == 1.0


async def test_exact_match_scores_zero_on_difference():
    result = await ExactMatchScorer().score(
        input="capital of France?", expected="Paris", actual="Lyon"
    )
    assert result.score == 0.0


def test_exact_match_is_marked_deterministic():
    # This flag is what stops the runner routing exact-match cases to humans.
    assert ExactMatchScorer().deterministic is True
    assert LLMJudgeScorer(model="m").deterministic is False


@pytest.mark.parametrize(
    "raw",
    [
        '{"score": 0.5, "confidence": 0.4}',
        '```json\n{"score": 0.5, "confidence": 0.4}\n```',
        '```\n{"score": 0.5, "confidence": 0.4}\n```',
        'Sure! Here is my judgment:\n{"score": 0.5, "confidence": 0.4}\nHope that helps.',
    ],
)
def test_judge_json_survives_the_ways_models_wrap_it(raw):
    assert _parse_json(raw) == {"score": 0.5, "confidence": 0.4}


async def test_judge_returns_parsed_score_and_confidence(fake_llm):
    fake_llm.judge("is a hot dog a sandwich?", score=0.4, confidence=0.2, reasoning="ambiguous")

    result = await LLMJudgeScorer(model="m").score(
        input="is a hot dog a sandwich?", expected="ambiguous", actual="yes"
    )

    assert result.score == 0.4
    assert result.confidence == 0.2
    assert result.reasoning == "ambiguous"


def test_unknown_scorer_is_rejected():
    with pytest.raises(ValueError, match="Unknown scorer"):
        get_scorer("vibes")
