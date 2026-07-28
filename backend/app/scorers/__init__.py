from app.scorers.exact_match import ExactMatchScorer
from app.scorers.llm_judge import LLMJudgeScorer


def get_scorer(name: str, model: str | None = None):
    if name == "exact_match":
        return ExactMatchScorer()
    if name == "llm_judge":
        return LLMJudgeScorer(model=model)
    raise ValueError(f"Unknown scorer: {name}")