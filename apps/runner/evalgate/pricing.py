"""Per-token model pricing, supplied by deployment rather than hardcoded.

Rates move whenever a provider reprices, so they are configuration, not
source. MODEL_PRICING is a JSON object mapping a model id to an
[input, output] pair of per-token costs:

    MODEL_PRICING='{"some-model": [3e-6, 15e-6]}'

A model absent from the table is costed at zero. An unpriced run still
completes and simply reports no spend, which is the right failure: a run
that refuses to finish because nobody updated a price table is worse than
one that under-reports cost.
"""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("pricing")

Rate = tuple[float, float]

_BUILTIN: dict[str, Rate] = {"mock-model": (0.0, 0.0)}


def _load() -> dict[str, Rate]:
    raw = os.getenv("MODEL_PRICING")
    if not raw:
        return dict(_BUILTIN)

    table = dict(_BUILTIN)
    try:
        parsed = json.loads(raw)
        for model, pair in parsed.items():
            cin, cout = pair
            table[model] = (float(cin), float(cout))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        # Bad pricing config must not take the worker down. Cost reporting
        # degrades to zero; scoring is unaffected.
        log.warning("ignoring malformed MODEL_PRICING (%s)", exc)
        return dict(_BUILTIN)

    return table


PRICING: dict[str, Rate] = _load()


def rate(model: str) -> Rate:
    return PRICING.get(model, (0.0, 0.0))


def cost(input_tokens: int, output_tokens: int, model: str) -> float:
    cin, cout = rate(model)
    return input_tokens * cin + output_tokens * cout
