from functools import lru_cache

from anthropic import AsyncAnthropic

from app.config import settings


class MissingAPIKey(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client() -> AsyncAnthropic:
    """Build the Anthropic client on first use.

    Deliberately lazy: constructing this at import time would make every test
    and every `--help` invocation depend on a configured key.
    """
    if not settings.anthropic_api_key:
        raise MissingAPIKey(
            "ANTHROPIC_API_KEY is not set. Copy backend/.env.example to "
            "backend/.env and fill it in."
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


async def complete(
    model: str,
    user: str,
    system: str | None = None,
    max_tokens: int = 1024,
) -> str:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user}],
    }
    if system:
        kwargs["system"] = system

    resp = await get_client().messages.create(**kwargs)
    return "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip()
