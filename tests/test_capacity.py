"""Capacity endpoint (/api/capacity): super-admin only; returns tier limits, per-turn cost,
and server config. Requires Postgres (skips otherwise), like the rest of the API suite."""
import pytest

from app import db
from app.config import ADMIN_PASSWORD


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        db.init_db()
        if not db.ping():
            pytest.skip("no database reachable")
    except Exception:
        pytest.skip("no database reachable")


def _client():
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


def _super():
    c = _client()
    assert c.post("/api/login", json={"username": "", "password": ADMIN_PASSWORD}).status_code == 200
    return c


def test_requires_auth():
    assert _client().get("/api/capacity").status_code == 401


def test_super_payload_shape(monkeypatch):
    # Avoid a real Anthropic probe in tests — force the defaults path.
    import app.capacity as cap
    monkeypatch.setattr(cap, "rate_limits", lambda *a, **k: None)
    body = _super().get("/api/capacity").json()
    tier = body["tier"]
    assert tier["requests_per_min"] == 50 and tier["input_tpm"] == 30000 and tier["output_tpm"] == 8000
    assert tier["live"] is False
    pt = body["per_turn"]
    for k in ("llm_calls", "input_tokens", "output_tokens", "seconds"):
        assert pt[k] > 0, k
    srv = body["server"]
    assert srv["threads"] >= 1 and srv["replicas"] >= 1 and srv["db_pool_max"] >= 1


def test_rate_limits_probe_is_cached(monkeypatch):
    import app.capacity as cap
    cap._cache["limits"] = None
    cap._cache["at"] = 0.0
    calls = {"n": 0}

    def fake_probe():
        calls["n"] += 1
        return {"model": "m", "requests_per_min": 4000, "input_tpm": 2_000_000, "output_tpm": 400_000}

    monkeypatch.setattr(cap, "_probe", fake_probe)
    a = cap.rate_limits()
    b = cap.rate_limits()                       # second call within TTL → cached, no re-probe
    assert a == b and a["requests_per_min"] == 4000
    assert calls["n"] == 1
