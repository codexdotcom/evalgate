from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", protected_namespaces=()
    )

    database_url: str = "postgresql+asyncpg://evalgate:evalgate@localhost:5432/evalgate"
    anthropic_api_key: str = ""
    default_model: str = "claude-haiku-4-5-20251001"   # model under evaluation
    judge_model: str = "claude-sonnet-5"               # the LLM judge
    default_confidence_threshold: float = 0.75
    pass_threshold: float = 0.7

    # Cases evaluated in parallel. Each one costs two API calls (generate +
    # judge), so this is the main lever on wall-clock time for a large dataset.
    max_concurrency: int = 5

    # Share of cases that must pass for a run to be certified. A run with any
    # unresolved review item is blocked regardless of this number.
    gate_pass_rate: float = 0.9


settings = Settings()