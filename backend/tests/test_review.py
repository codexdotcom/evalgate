import uuid

HOT_DOG = "is a hot dog a sandwich?"


async def _run_with_one_uncertain_case(client, dataset, fake_llm):
    fake_llm.answer(HOT_DOG, "yes, obviously")
    fake_llm.judge(HOT_DOG, score=0.5, confidence=0.2, reasoning="genuinely ambiguous")

    resp = await client.post(
        "/runs",
        json={
            "dataset_id": dataset["id"],
            "scorer": "llm_judge",
            "confidence_threshold": 0.75,
        },
    )
    return resp.json()["id"]


async def test_unconfident_judgment_lands_in_the_queue(client, dataset, fake_llm):
    await _run_with_one_uncertain_case(client, dataset, fake_llm)

    queue = (await client.get("/review")).json()

    assert len(queue) == 1
    item = queue[0]
    assert item["status"] == "pending"
    assert item["confidence"] == 0.2


async def test_queue_carries_enough_context_to_actually_review(client, dataset, fake_llm):
    await _run_with_one_uncertain_case(client, dataset, fake_llm)

    item = (await client.get("/review")).json()[0]

    # A reviewer should not have to go fetch the case separately.
    assert item["input"] == HOT_DOG
    assert item["expected_output"] == "ambiguous"
    assert item["model_output"] == "yes, obviously"
    assert item["reasoning"] == "genuinely ambiguous"


async def test_confident_judgments_stay_out_of_the_queue(client, dataset, fake_llm):
    await client.post(
        "/runs",
        json={
            "dataset_id": dataset["id"],
            "scorer": "llm_judge",
            "confidence_threshold": 0.75,
        },
    )
    assert (await client.get("/review")).json() == []


async def test_resolving_overrides_the_machine_verdict(client, dataset, fake_llm):
    run_id = await _run_with_one_uncertain_case(client, dataset, fake_llm)
    item = (await client.get("/review")).json()[0]

    resp = await client.post(
        f"/review/{item['id']}/resolve",
        json={"verdict": "pass", "reviewer": "ada", "notes": "close enough"},
    )
    assert resp.status_code == 200
    assert resp.json()["resolved_at"] is not None

    results = (await client.get(f"/runs/{run_id}/results")).json()
    reviewed = [r for r in results if r["id"] == item["result_id"]][0]
    assert reviewed["verdict"] == "pass"


async def test_resolution_is_appended_to_the_audit_trail(client, dataset, fake_llm):
    run_id = await _run_with_one_uncertain_case(client, dataset, fake_llm)
    item = (await client.get("/review")).json()[0]

    await client.post(
        f"/review/{item['id']}/resolve",
        json={"verdict": "fail", "reviewer": "ada"},
    )

    results = (await client.get(f"/runs/{run_id}/results")).json()
    reviewed = [r for r in results if r["id"] == item["result_id"]][0]
    # The judge's original reasoning must survive alongside the human's call.
    assert "genuinely ambiguous" in reviewed["reasoning"]
    assert "[human-review] ada: fail" in reviewed["reasoning"]


async def test_resolved_items_leave_the_pending_queue(client, dataset, fake_llm):
    await _run_with_one_uncertain_case(client, dataset, fake_llm)
    item = (await client.get("/review")).json()[0]

    await client.post(
        f"/review/{item['id']}/resolve", json={"verdict": "pass", "reviewer": "ada"}
    )

    assert (await client.get("/review")).json() == []
    assert len((await client.get("/review?status=all")).json()) == 1


async def test_a_verdict_cannot_be_silently_overwritten(client, dataset, fake_llm):
    await _run_with_one_uncertain_case(client, dataset, fake_llm)
    item = (await client.get("/review")).json()[0]

    await client.post(
        f"/review/{item['id']}/resolve", json={"verdict": "pass", "reviewer": "ada"}
    )
    second = await client.post(
        f"/review/{item['id']}/resolve", json={"verdict": "fail", "reviewer": "bob"}
    )

    assert second.status_code == 400


async def test_a_human_cannot_answer_needs_review(client, dataset, fake_llm):
    await _run_with_one_uncertain_case(client, dataset, fake_llm)
    item = (await client.get("/review")).json()[0]

    resp = await client.post(
        f"/review/{item['id']}/resolve",
        json={"verdict": "needs_review", "reviewer": "ada"},
    )
    assert resp.status_code == 422


async def test_resolving_a_missing_item_is_404(client):
    resp = await client.post(
        f"/review/{uuid.uuid4()}/resolve",
        json={"verdict": "pass", "reviewer": "ada"},
    )
    assert resp.status_code == 404
