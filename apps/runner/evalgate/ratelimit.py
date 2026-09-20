from __future__ import annotations
import asyncio, logging, os, random, time

import anthropic

log = logging.getLogger("ratelimit")

MAX_RETRIES = int(os.getenv("MODEL_MAX_RETRIES", "6"))
BASE_DELAY = float(os.getenv("MODEL_BASE_DELAY", "1.0"))
MAX_DELAY = float(os.getenv("MODEL_MAX_DELAY", "60.0"))

# Process-wide gate. When one request gets a 429, every coroutine in this
# worker waits until that window passes instead of all retrying into the
# same limit. One shared clock beats N independent backoffs.
_gate_until: float = 0.0
_gate_lock = asyncio.Lock()


async def _wait_for_gate() -> None:
    while True:
        async with _gate_lock:
            remaining = _gate_until - time.monotonic()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, 5.0))


async def _close_gate(seconds: float) -> None:
    async with _gate_lock:
        globals()["_gate_until"] = max(_gate_until, time.monotonic() + seconds)


def _retry_after(exc: Exception) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    for key in ("retry-after", "anthropic-ratelimit-requests-reset"):
        raw = headers.get(key)
        if raw:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


async def call_model(fn, /, **kwargs):
    """Wrap an Anthropic SDK call with failure-aware backoff.

    429 and 529  -> honour retry-after, close the shared gate, full jitter
    5xx / timeout -> exponential backoff, no gate (it is not a quota problem)
    400 / 401    -> raise immediately, retrying a bad request wastes budget
    """
    attempt = 0
    while True:
        await _wait_for_gate()
        try:
            return await fn(**kwargs)

        except (anthropic.RateLimitError, anthropic.APIStatusError) as exc:
            status = getattr(exc, "status_code", None)

            if isinstance(exc, anthropic.APIStatusError) and status not in (429, 529, None) and status < 500:
                raise  # 400, 401, 403, 404: not retryable

            attempt += 1
            if attempt > MAX_RETRIES:
                raise

            hinted = _retry_after(exc)
            delay = hinted if hinted is not None else min(
                MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1))
            )
            delay = random.uniform(0, delay)  # full jitter
            log.warning("rate limited (status=%s), gating %.1fs (attempt %d)", status, delay, attempt)
            await _close_gate(delay)
            await asyncio.sleep(delay)

        except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.InternalServerError) as exc:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            delay = random.uniform(0, min(MAX_DELAY, BASE_DELAY * (2 ** (attempt - 1))))
            log.warning("transient error %s, retrying in %.1fs (attempt %d)",
                        type(exc).__name__, delay, attempt)
            await asyncio.sleep(delay)  # no gate: this is not a quota signal