"""Convert nebius/SWE-agent-trajectories into EvalGate JSONL.

Source: https://huggingface.co/datasets/nebius/SWE-agent-trajectories (CC-BY-4.0)
Each output record carries a recorded trajectory, so the harness scores it in
replay mode with zero model calls, plus the execution-verified outcome as
ground truth for calibration.
"""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
from typing import Any

from datasets import load_dataset

# Adjust after inspecting the schema. Each value is a tuple of candidate keys,
# tried in order, so a rename upstream does not break the whole script.
FIELD_MAP = {
    "instance_id": ("instance_id", "id", "task_id"),
    "problem": ("problem_statement", "issue", "prompt", "text"),
    "trajectory": ("trajectory", "messages", "history", "steps"),
    "resolved": ("resolved", "is_resolved", "success", "passed"),
    "patch": ("model_patch", "patch", "prediction"),
    "repo": ("repo", "repository"),
}


def pick(row: dict, key: str) -> Any:
    for candidate in FIELD_MAP[key]:
        if candidate in row and row[candidate] not in (None, ""):
            return row[candidate]
    return None


def as_list(raw: Any) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = raw.get("steps") or raw.get("messages") or raw.get("history") or []
    return raw if isinstance(raw, list) else []


def to_steps(raw: Any) -> list[dict]:
    """SWE-agent records alternating thought/action/observation. Normalize into
    the canonical step shape; execute.normalize_trajectory handles the rest."""
    steps: list[dict] = []
    for entry in as_list(raw):
        if not isinstance(entry, dict):
            continue

        role = entry.get("role", "assistant")
        content = entry.get("content") or entry.get("thought") or ""
        if isinstance(content, list):  # content-block form
            content = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )

        tool_calls = []
        action = entry.get("action") or entry.get("tool_calls")
        if isinstance(action, str) and action.strip():
            # SWE-agent actions are bash-ish command strings: "open foo.py 12"
            name = action.strip().split()[0]
            tool_calls = [{"id": f"t{len(steps)}", "name": name, "args": {"cmd": action.strip()}}]
        elif isinstance(action, list):
            for i, tc in enumerate(action):
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                tool_calls.append({
                    "id": str(tc.get("id", f"t{len(steps)}-{i}")),
                    "name": tc.get("name") or fn.get("name") or "unknown",
                    "args": tc.get("args") or tc.get("input") or fn.get("arguments") or {},
                })

        observation = entry.get("observation") or entry.get("tool_result")

        steps.append({
            "role": "tool" if (observation and not content and not tool_calls) else role,
            "content": str(content)[:4000],
            "tool_calls": tool_calls,
            "tool_result": str(observation)[:2000] if observation else None,
        })
    return steps


RUBRIC = (
    "The agent resolved the GitHub issue: it located the relevant code, made a "
    "targeted edit that addresses the described problem, and did not leave the "
    "repository in a broken state. Repeated identical commands, editing unrelated "
    "files, or submitting without a substantive change do not count as resolved."
)


def convert(n: int, out: Path, seed: int, balance: float) -> None:
    ds = load_dataset("nebius/SWE-agent-trajectories", split="train", streaming=True)
    rnd = random.Random(seed)

    want_resolved = int(n * balance)
    want_failed = n - want_resolved
    kept_resolved, kept_failed = [], []
    scanned = 0

    for row in ds:
        scanned += 1
        if scanned > 40000:
            break

        steps = to_steps(pick(row, "trajectory"))
        if len(steps) < 2:
            continue

        resolved = bool(pick(row, "resolved"))
        bucket = kept_resolved if resolved else kept_failed
        limit = want_resolved if resolved else want_failed
        if len(bucket) >= limit:
            if len(kept_resolved) >= want_resolved and len(kept_failed) >= want_failed:
                break
            continue

        problem = str(pick(row, "problem") or "").strip()
        if not problem:
            continue

        bucket.append({
            "id": str(pick(row, "instance_id") or f"swe-{scanned}"),
            "prompt": problem[:6000],
            "rubric": RUBRIC,
            "tags": ["swe-bench", str(pick(row, "repo") or "unknown"),
                     "resolved" if resolved else "unresolved"],
            "trajectory": {
                "steps": steps,
                "final_output": str(pick(row, "patch") or "")[:4000],
                "terminal_state": "completed" if resolved else "max_steps",
            },
            # Ground truth from test execution. Not a scorer input: this is the
            # objective anchor calibration is measured against.
            "ground_truth": {"resolved": resolved, "source": "pr_tests"},
        })

    records = kept_resolved + kept_failed
    rnd.shuffle(records)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    print(f"scanned {scanned} rows")
    print(f"wrote {len(records)} cases to {out}")
    print(f"  resolved:   {len(kept_resolved)}")
    print(f"  unresolved: {len(kept_failed)}")
    if len(records) < n:
        print(f"WARNING: wanted {n}, got {len(records)}. Raise the scan cap.", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(prog="evalgate-convert-swebench")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--out", type=Path, default=Path("datasets/swebench-200.jsonl"))
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--balance", type=float, default=0.45,
                   help="fraction resolved; near 0.5 keeps kappa meaningful")
    convert(**vars(p.parse_args()))


if __name__ == "__main__":
    main()