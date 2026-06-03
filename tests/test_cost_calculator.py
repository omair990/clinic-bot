"""Cost calculator endpoint (/api/cost-calculator): super-admin only, returns volumes + rate
defaults. Requires Postgres (skips otherwise), matching the rest of the API test suite."""
import uuid

import pytest

from app import db
from app.auth import hash_password
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
    assert _client().get("/api/cost-calculator").status_code == 401


def test_clinic_login_forbidden():
    tid = db.create_tenant(f"Calc {uuid.uuid4().hex[:6]}", f"calc-{uuid.uuid4().hex[:6]}",
                           None, 1, "Asia/Riyadh", None, {"clinic": {"name": "X"}})
    uname = "calcstaff-" + uuid.uuid4().hex[:8]
    db.set_tenant_credentials(tid, uname, hash_password("pw"))
    c = _client()
    assert c.post("/api/login", json={"username": uname, "password": "pw"}).status_code == 200
    assert c.get("/api/cost-calculator").status_code == 403


def test_super_gets_volumes_and_defaults():
    r = _super().get("/api/cost-calculator")
    assert r.status_code == 200
    body = r.json()
    assert "period" in body and "model" in body
    # Volume totals are present and non-negative; headline "messages" == inbound.
    tot = body["totals"]
    for k in ("inbound", "voice", "replies", "reminders", "messages"):
        assert tot[k] >= 0, k
    assert tot["messages"] == tot["inbound"]
    # Rate defaults the UI needs are present and numeric.
    d = body["defaults"]
    for k in ("usd_to_sar", "claude_input_usd_per_mtok", "claude_output_usd_per_mtok",
              "avg_input_tokens_per_inquiry", "avg_output_tokens_per_inquiry",
              "whatsapp_sar_per_conversation", "messages_per_conversation",
              "whatsapp_sar_per_reminder", "reminders_per_inquiry", "replies_per_inquiry",
              "voice_sar_per_message", "railway_usd_per_month"):
        assert isinstance(d[k], (int, float)), k
    # Per-clinic exact usage carries the real breakdown fields.
    assert isinstance(body["clinics"], list)
    for c in body["clinics"]:
        for k in ("inbound", "voice", "replies", "reminders"):
            assert k in c, k


def test_claude_price_default_by_tier():
    from app.api import _claude_price_default
    assert _claude_price_default("claude-opus-4-8")["input"] == 15.0
    assert _claude_price_default("claude-sonnet-4-6")["input"] == 3.0
    assert _claude_price_default("claude-haiku-4-5")["input"] == 1.0
    assert _claude_price_default("something-unknown") == _claude_price_default("claude-sonnet-4-6")
