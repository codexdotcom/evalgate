import pytest
from evalgate.scorers import ToolCallSequence, NoLoops, StepBudget

def traj(tool_names):
    return {
        "steps": [
            {"index": i, "role": "assistant", "content": "",
             "tool_calls": [{"id": f"t{i}", "name": n, "args": {}}]}
            for i, n in enumerate(tool_names)
        ],
        "final_output": "", "terminal_state": "completed",
    }

@pytest.mark.asyncio
async def test_tool_sequence_exact():
    r = await ToolCallSequence().score(
        traj(["search", "finish"]), {"expected": {"tool_sequence": ["search", "finish"]}})
    assert r.passed and r.value == 1.0

@pytest.mark.asyncio
async def test_tool_sequence_partial_credit():
    r = await ToolCallSequence().score(
        traj(["search", "read", "finish"]),
        {"expected": {"tool_sequence": ["search", "write", "finish"]}})
    assert not r.passed and 0 < r.value < 1

@pytest.mark.asyncio
async def test_no_loops_flags_three_identical():
    r = await NoLoops().score(traj(["search", "search", "search"]), {})
    assert not r.passed

@pytest.mark.asyncio
async def test_no_loops_allows_two():
    r = await NoLoops().score(traj(["search", "search", "finish"]), {})
    assert r.passed

@pytest.mark.asyncio
async def test_step_budget():
    assert not (await StepBudget(max_steps=2).score(traj(["a","b","c"]), {})).passed