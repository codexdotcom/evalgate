from __future__ import annotations
import json, os, time
from typing import Any, Callable, Awaitable

from anthropic import AsyncAnthropic
from .ratelimit import call_model  # shared retry/backoff, see section 3

client = AsyncAnthropic()

MAX_STEPS = int(os.getenv("MAX_STEPS", "20"))

# Pricing per token, input/output. Extend as you add models.
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0 / 1e6, 15.0 / 1e6),
    "claude-haiku-4-5": (1.0 / 1e6, 5.0 / 1e6),
    "mock-model": (0.0, 0.0),
}


# ------------------------------------------------------------------ #
# Tools. Swap this registry for a real sandbox when you have one.
# ------------------------------------------------------------------ #

ToolFn = Callable[[dict[str, Any]], Awaitable[str]]

async def _search(args: dict) -> str:
    return f"3 results for {args.get('query', '')}"

async def _read_file(args: dict) -> str:
    return f"contents of {args.get('path', 'unknown')}"

async def _finish(args: dict) -> str:
    return args.get("answer", "")

TOOLS: dict[str, ToolFn] = {
    "search": _search,
    "read_file": _read_file,
    "finish": _finish,
}

TOOL_SCHEMAS = [
    {
        "name": "search",
        "description": "Search the corpus for relevant documents.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file by path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "finish",
        "description": "Submit the final answer and end the episode.",
        "input_schema": {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    },
]


# ------------------------------------------------------------------ #
# Replay
# ------------------------------------------------------------------ #

def normalize_trajectory(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept a recorded trajectory in loose form and return the canonical
    shape the scorers expect. Tolerant on input, strict on output: this is
    the seam where other people's data enters the harness."""
    steps_in = raw.get("steps") or raw.get("messages") or []
    steps: list[dict[str, Any]] = []

    for i, s in enumerate(steps_in):
        tool_calls = []
        for tc in s.get("tool_calls") or s.get("toolCalls") or []:
            args = tc.get("args") or tc.get("input") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            tool_calls.append({
                "id": str(tc.get("id", f"t{i}")),
                "name": tc.get("name") or tc.get("function", {}).get("name", "unknown"),
                "args": args,
            })

        steps.append({
            "index": i,
            "role": s.get("role", "assistant"),
            "content": s.get("content") or "",
            "tool_calls": tool_calls,
            "tool_result": s.get("tool_result") or s.get("toolResult"),
            "latency_ms": int(s.get("latency_ms") or s.get("latencyMs") or 0),
            "input_tokens": int(s.get("input_tokens") or s.get("inputTokens") or 0),
            "output_tokens": int(s.get("output_tokens") or s.get("outputTokens") or 0),
        })

    final = raw.get("final_output") or raw.get("finalOutput") or ""
    if not final and steps:
        final = steps[-1]["content"]

    return {
        "steps": steps,
        "final_output": final,
        "terminal_state": raw.get("terminal_state") or raw.get("terminalState") or "completed",
        "replayed": True,
    }


# ------------------------------------------------------------------ #
# Live agent loop
# ------------------------------------------------------------------ #

async def _live(case: dict[str, Any], model: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "user", "content": case["prompt"]}]
    steps: list[dict[str, Any]] = []
    final_output = ""
    terminal = "max_steps"
    idx = 0

    for _ in range(MAX_STEPS):
        t0 = time.perf_counter()
        resp = await call_model(
            client.messages.create,
            model=model,
            max_tokens=2048,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        latency = int((time.perf_counter() - t0) * 1000)

        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [b for b in resp.content if b.type == "tool_use"]

        steps.append({
            "index": idx,
            "role": "assistant",
            "content": text,
            "tool_calls": [{"id": c.id, "name": c.name, "args": dict(c.input)} for c in calls],
            "tool_result": None,
            "latency_ms": latency,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        })
        idx += 1

        if not calls:
            final_output, terminal = text, "completed"
            break

        messages.append({"role": "assistant", "content": resp.content})
        results_block = []

        for c in calls:
            fn = TOOLS.get(c.name)
            if fn is None:
                out, is_error = f"unknown tool: {c.name}", True
            else:
                try:
                    out, is_error = await fn(dict(c.input)), False
                except Exception as exc:  # noqa: BLE001
                    out, is_error = f"tool error: {exc}", True

            steps.append({
                "index": idx, "role": "tool", "content": "",
                "tool_calls": [], "tool_result": out,
                "latency_ms": 0, "input_tokens": 0, "output_tokens": 0,
            })
            idx += 1
            results_block.append({
                "type": "tool_result", "tool_use_id": c.id,
                "content": out, "is_error": is_error,
            })

        messages.append({"role": "user", "content": results_block})

        finish = next((c for c in calls if c.name == "finish"), None)
        if finish:
            final_output = dict(finish.input).get("answer", "")
            terminal = "completed"
            break

    return {
        "steps": steps,
        "final_output": final_output,
        "terminal_state": terminal,
        "replayed": False,
    }


async def _mock(case: dict[str, Any]) -> dict[str, Any]:
    """Zero-cost path for load testing. Keeps the loadtest honest about
    harness throughput without measuring the model provider."""
    import random
    rnd = random.Random(hash(case["prompt"]) & 0xFFFFFFFF)
    n = rnd.randint(2, 8)
    steps = [{
        "index": i, "role": "assistant" if i % 2 == 0 else "tool",
        "content": f"step {i}" if i % 2 == 0 else "",
        "tool_calls": ([{"id": f"t{i}", "name": rnd.choice(list(TOOLS)), "args": {}}]
                       if i % 2 == 0 else []),
        "tool_result": None if i % 2 == 0 else "ok",
        "latency_ms": rnd.randint(50, 400),
        "input_tokens": rnd.randint(200, 1200), "output_tokens": rnd.randint(30, 300),
    } for i in range(n)]
    return {"steps": steps, "final_output": "done",
            "terminal_state": "completed", "replayed": False}


def cost_of(traj: dict, model: str) -> float:
    cin, cout = PRICING.get(model, (0.0, 0.0))
    return sum(s["input_tokens"] * cin + s["output_tokens"] * cout for s in traj["steps"])


async def run_agent(case: dict[str, Any], model: str) -> dict[str, Any]:
    """Three modes, resolved in priority order:
      1. case carries a recorded trajectory  -> replay, no model call
      2. model == 'mock-model'               -> synthetic, no model call
      3. otherwise                           -> live agent loop
    """
    recorded = case.get("trajectory") or (case.get("expected") or {}).get("trajectory")
    if recorded:
        traj = normalize_trajectory(recorded)
    elif model == "mock-model":
        traj = await _mock(case)
    else:
        traj = await _live(case, model)

    traj["cost_usd"] = cost_of(traj, model)
    return traj