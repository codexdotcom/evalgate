import uuid


async def test_create_dataset_returns_its_cases(client):
    resp = await client.post(
        "/datasets",
        json={
            "name": "smoke",
            "description": "d",
            "cases": [
                {"input": "a", "expected_output": "1"},
                {"input": "b", "expected_output": "2", "metadata": {"tag": "math"}},
            ],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "smoke"
    assert [c["input"] for c in body["cases"]] == ["a", "b"]


async def test_case_metadata_round_trips_through_its_alias(client):
    # Stored as case_metadata to dodge SQLAlchemy's reserved `metadata`, but
    # the API contract says `metadata`.
    resp = await client.post(
        "/datasets",
        json={
            "name": "meta",
            "cases": [{"input": "a", "expected_output": "1", "metadata": {"tag": "x"}}],
        },
    )
    dataset_id = resp.json()["id"]

    fetched = (await client.get(f"/datasets/{dataset_id}")).json()
    assert fetched["cases"][0]["metadata"] == {"tag": "x"}


async def test_list_datasets_reports_case_counts(client, dataset):
    await client.post("/datasets", json={"name": "empty one", "cases": []})

    rows = (await client.get("/datasets")).json()
    by_name = {d["name"]: d for d in rows}

    assert by_name["fixture dataset"]["case_count"] == 3
    assert by_name["empty one"]["case_count"] == 0


async def test_missing_dataset_is_404(client):
    resp = await client.get(f"/datasets/{uuid.uuid4()}")
    assert resp.status_code == 404
