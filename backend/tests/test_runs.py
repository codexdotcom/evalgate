import uuid

HOT_DOG = "is a hot dog a sandwich?"


async def _run(client, dataset, **overrides):
    """Start a run and return it once the background task has settled."""
    payload = {
        "dataset_id": dataset["id"],
        "scorer": "llm_judge",
        "confidence_threshold": 0.75,
        **overrides,
    }
    resp = await client.post("/runs", json=payload)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["id"]
    return (await client.get(f"/runs/{run_id}")).json()


async def test_run_is_pending_before_the_background_task_lands(client, dataset):
    resp = await client.post(
        "/runs", json={"dataset_id": dataset["id"], "scorer": "llm_judge"}
    )
    assert resp.json()["status"] == "pending"


async def test_run_produces_one_result_per_case(client, dataset, fake_llm):
    run = await _run(client, dataset)
    assert run["status"] == "completed"

    results = (await client.get(f"/runs/{run['id']}/results")).json()
    assert len(results) == 3
    assert {r["verdict"] for r in results} == {"pass"}


async def test_run_defaults_the_model_from_settings(client, dataset, fake_llm):
    from app.config import settings

    run = await _run(client, dataset)
    assert run["model"] == settings.default_model


async def test_low_score_becomes_a_fail_not_a_review(client, dataset, fake_llm):
    # Confident that it is wrong is a decision, not an escalation.
    fake_llm.judge(HOT_DOG, score=0.0, confidence=0.99)

    run = await _run(client, dataset)
    results = (await client.get(f"/runs/{run['id']}/results")).json()

    verdicts = sorted(r["verdict"] for r in results)
    assert verdicts == ["fail", "pass", "pass"]


async def test_exact_match_never_escalates(client, dataset, fake_llm):
    # Every answer is wrong, but a deterministic scorer has nothing to be
    # unsure about, so nothing should reach the queue.
    fake_llm.default_answer = "definitely not the expected string"

    run = await _run(client, dataset, scorer="exact_match")
    results = (await client.get(f"/runs/{run['id']}/results")).json()

    assert {r["verdict"] for r in results} == {"fail"}
    assert (await client.get("/review")).json() == []


async def test_one_failing_case_does_not_sink_the_run(client, dataset, fake_llm):
    fake_llm.fail(HOT_DOG)

    run = await _run(client, dataset)

    assert run["status"] == "completed"
    results = (await client.get(f"/runs/{run['id']}/results")).json()
    assert len(results) == 3

    errored = [r for r in results if r["reasoning"].startswith("[error]")]
    assert len(errored) == 1
    # An error is an absence of a verdict, so it escalates rather than failing.
    assert errored[0]["verdict"] == "needs_review"


async def test_run_fails_when_every_case_errors(client, dataset, fake_llm):
    for case in dataset["cases"]:
        fake_llm.fail(case["input"])

    run = await _run(client, dataset)

    # A tidy queue of "needs review" would hide what is really a bad API key.
    assert run["status"] == "failed"


async def test_run_against_unknown_dataset_is_404(client):
    resp = await client.post("/runs", json={"dataset_id": str(uuid.uuid4())})
    assert resp.status_code == 404


async def test_unknown_scorer_is_rejected(client, dataset):
    resp = await client.post(
        "/runs", json={"dataset_id": dataset["id"], "scorer": "vibes"}
    )
    assert resp.status_code == 422
