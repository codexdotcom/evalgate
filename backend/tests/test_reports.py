import random
import uuid
from types import SimpleNamespace

from sqlalchemy import select

from app.models import EvalResult
from app.services.report import compute_content_hash

HOT_DOG = "is a hot dog a sandwich?"


async def _start_run(client, dataset):
    resp = await client.post(
        "/runs",
        json={
            "dataset_id": dataset["id"],
            "scorer": "llm_judge",
            "confidence_threshold": 0.75,
        },
    )
    return resp.json()["id"]


async def test_all_passing_run_is_certified(client, dataset, fake_llm, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gate_pass_rate", 0.9)
    run_id = await _start_run(client, dataset)

    report = (await client.post(f"/runs/{run_id}/report")).json()

    assert report["summary"]["gate"] == "pass"
    assert report["summary"]["pass_rate"] == 1.0
    assert report["summary"]["total"] == 3


async def test_too_many_failures_fails_the_gate(client, dataset, fake_llm, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gate_pass_rate", 0.9)
    fake_llm.judge(HOT_DOG, score=0.0, confidence=0.99)
    run_id = await _start_run(client, dataset)

    report = (await client.post(f"/runs/{run_id}/report")).json()

    # 2/3 passing is short of the 90% bar.
    assert report["summary"]["gate"] == "fail"


async def test_pending_review_blocks_certification(client, dataset, fake_llm):
    fake_llm.judge(HOT_DOG, score=0.9, confidence=0.2)
    run_id = await _start_run(client, dataset)

    report = (await client.post(f"/runs/{run_id}/report")).json()

    # Two of three passed and the third might well have too, but the system
    # said it could not decide — that is not something to average away.
    assert report["summary"]["gate"] == "blocked"
    assert report["summary"]["needs_review"] == 1


async def test_human_resolution_unblocks_the_gate(client, dataset, fake_llm, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gate_pass_rate", 0.9)
    fake_llm.judge(HOT_DOG, score=0.9, confidence=0.2)
    run_id = await _start_run(client, dataset)

    item = (await client.get("/review")).json()[0]
    await client.post(
        f"/review/{item['id']}/resolve", json={"verdict": "pass", "reviewer": "ada"}
    )

    report = (await client.post(f"/runs/{run_id}/report")).json()

    assert report["summary"]["gate"] == "pass"
    assert report["summary"]["human_reviewed"] == 1


async def test_decided_pass_rate_excludes_undecided_cases(client, dataset, fake_llm):
    fake_llm.judge(HOT_DOG, score=0.9, confidence=0.2)
    run_id = await _start_run(client, dataset)

    summary = (await client.post(f"/runs/{run_id}/report")).json()["summary"]

    assert summary["pass_rate"] == round(2 / 3, 4)  # over everything
    assert summary["decided_pass_rate"] == 1.0  # over what we actually judged


async def test_regenerating_over_unchanged_results_reproduces_the_hash(
    client, dataset, fake_llm
):
    run_id = await _start_run(client, dataset)

    first = (await client.post(f"/runs/{run_id}/report")).json()
    second = (await client.post(f"/runs/{run_id}/report")).json()

    assert first["content_hash"] == second["content_hash"]
    assert first["id"] != second["id"]


def test_hash_ignores_the_order_results_come_back_in():
    """The end-to-end test above cannot catch this.

    SQLite hands rows back in rowid order, so it looks stable no matter what.
    Postgres has no such obligation for rows sharing a created_at, which is
    every row in a run. Pin the property directly instead.
    """
    run = SimpleNamespace(
        id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        model="claude-haiku-4-5-20251001",
        scorer="llm_judge",
        confidence_threshold=0.75,
    )
    results = [
        SimpleNamespace(case_id=uuid.uuid4(), verdict="pass", score=1.0, confidence=0.9)
        for _ in range(8)
    ]
    summary = {"total": 8, "pass": 8, "fail": 0, "needs_review": 0}

    shuffled = results[:]
    random.shuffle(shuffled)

    assert compute_content_hash(run, results, summary) == compute_content_hash(
        run, shuffled, summary
    )


def test_hash_still_moves_when_a_verdict_moves():
    run = SimpleNamespace(
        id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        model="m",
        scorer="llm_judge",
        confidence_threshold=0.75,
    )
    case_id = uuid.uuid4()
    summary = {"total": 1, "pass": 1, "fail": 0, "needs_review": 0}

    passing = [SimpleNamespace(case_id=case_id, verdict="pass", score=1.0, confidence=0.9)]
    failing = [SimpleNamespace(case_id=case_id, verdict="fail", score=1.0, confidence=0.9)]

    assert compute_content_hash(run, passing, summary) != compute_content_hash(
        run, failing, summary
    )


async def test_an_altered_verdict_changes_the_hash(
    client, dataset, fake_llm, sessionmaker_
):
    run_id = await _start_run(client, dataset)
    before = (await client.post(f"/runs/{run_id}/report")).json()["content_hash"]

    async with sessionmaker_() as db:
        result = (
            await db.execute(select(EvalResult).where(EvalResult.run_id == uuid.UUID(run_id)))
        ).scalars().first()
        result.verdict = "fail"
        await db.commit()

    after = (await client.post(f"/runs/{run_id}/report")).json()["content_hash"]

    assert before != after


async def test_a_failed_run_cannot_be_certified(client, dataset, fake_llm):
    for case in dataset["cases"]:
        fake_llm.fail(case["input"])
    run_id = await _start_run(client, dataset)

    resp = await client.post(f"/runs/{run_id}/report")

    assert resp.status_code == 400


async def test_latest_report_is_the_one_returned(client, dataset, fake_llm):
    run_id = await _start_run(client, dataset)
    assert (await client.get(f"/runs/{run_id}/report")).status_code == 404

    created = (await client.post(f"/runs/{run_id}/report")).json()
    fetched = (await client.get(f"/runs/{run_id}/report")).json()

    assert fetched["id"] == created["id"]
