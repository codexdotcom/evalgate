import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 — registers tables on Base.metadata
from app.database import Base, get_db
from app.main import app
from app.scorers.llm_judge import JUDGE_SYSTEM
from app.services import llm_client, runner


@pytest_asyncio.fixture
async def engine():
    # StaticPool keeps one connection alive for the whole test; without it each
    # checkout gets a fresh, empty :memory: database.
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker_(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


class FakeLLM:
    """Stands in for Anthropic for both roles the runner plays.

    The model under test and the judge are told apart by their system prompt,
    which is how the real code distinguishes them too.
    """

    def __init__(self):
        self.answers: dict[str, str] = {}
        self.judgments: dict[str, tuple[float, float, str]] = {}
        self.default_answer = "a plausible answer"
        self.default_judgment = (1.0, 0.95, "matches expected")
        self.fail_on: set[str] = set()
        self.calls: list[dict] = []

    def answer(self, case_input: str, output: str):
        self.answers[case_input] = output
        return self

    def judge(self, case_input: str, score: float, confidence: float, reasoning="r"):
        self.judgments[case_input] = (score, confidence, reasoning)
        return self

    def fail(self, case_input: str):
        self.fail_on.add(case_input)
        return self

    async def complete(self, model, user, system=None, max_tokens=1024):
        self.calls.append({"model": model, "system": system, "user": user})

        if system == JUDGE_SYSTEM:
            for case_input, verdict in self.judgments.items():
                # The judge prompt embeds the case input verbatim.
                if case_input in user:
                    score, confidence, reasoning = verdict
                    break
            else:
                score, confidence, reasoning = self.default_judgment
            return json.dumps(
                {"score": score, "confidence": confidence, "reasoning": reasoning}
            )

        if user in self.fail_on:
            raise RuntimeError("simulated upstream failure")
        return self.answers.get(user, self.default_answer)


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    # Both the runner and the judge scorer resolve `complete` off the module at
    # call time, so one patch covers both.
    monkeypatch.setattr(llm_client, "complete", fake.complete)
    return fake


@pytest_asyncio.fixture
async def client(sessionmaker_, monkeypatch, fake_llm):
    async def override_get_db():
        async with sessionmaker_() as session:
            yield session

    # execute_run runs outside the request scope and opens its own session, so
    # the dependency override alone would leave it pointed at the real engine.
    monkeypatch.setattr(runner, "AsyncSessionLocal", sessionmaker_)
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def dataset(client):
    """A three-case dataset; cases are addressed by input text in tests."""
    resp = await client.post(
        "/datasets",
        json={
            "name": "fixture dataset",
            "description": "for tests",
            "cases": [
                {"input": "capital of France?", "expected_output": "Paris"},
                {"input": "17 times 3?", "expected_output": "51"},
                {"input": "is a hot dog a sandwich?", "expected_output": "ambiguous"},
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
