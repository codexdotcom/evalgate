import importlib

from evalgate import pricing


def reload_with(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MODEL_PRICING", raising=False)
    else:
        monkeypatch.setenv("MODEL_PRICING", value)
    return importlib.reload(pricing)


def test_unconfigured_costs_nothing(monkeypatch):
    p = reload_with(monkeypatch, None)
    assert p.rate("anything") == (0.0, 0.0)
    assert p.cost(1000, 1000, "anything") == 0.0


def test_reads_table_from_env(monkeypatch):
    p = reload_with(monkeypatch, '{"m": [2e-6, 10e-6]}')
    assert p.cost(1_000_000, 1_000_000, "m") == 12.0


def test_unknown_model_is_free(monkeypatch):
    p = reload_with(monkeypatch, '{"m": [2e-6, 10e-6]}')
    assert p.cost(1_000_000, 0, "other") == 0.0


def test_malformed_table_does_not_raise(monkeypatch):
    p = reload_with(monkeypatch, "not json")
    assert p.rate("m") == (0.0, 0.0)
    reload_with(monkeypatch, None)
