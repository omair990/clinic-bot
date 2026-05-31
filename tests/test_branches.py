"""Unit tests for multi-branch routing (find_branch tool + prompt block). No DB/network."""
from app.prompts import build_system_prompt
from app.tools import AgentContext, dispatch

CLINIC = {
    "clinic": {"name": "Multi Clinic"},
    "branches": [
        {"name": "Olaya", "city": "Riyadh", "district": "Al-Olaya", "address": "Olaya St",
         "phone": "+1", "services": ["Dental Checkup", "Consult"]},
        {"name": "Naseem", "city": "Riyadh", "district": "Al-Naseem", "address": "KAR",
         "phone": "+2", "services": ["Consult"]},
        {"name": "Jeddah", "city": "Jeddah", "district": "Corniche", "address": "Corniche Rd",
         "phone": "+3", "services": ["Dental Checkup"]},
    ],
}


def _ctx(clinic=CLINIC):
    return AgentContext(wa_user="x", tenant_id=0, clinic_data=clinic)


def test_find_branch_matches_city():
    out = dispatch("find_branch", {"location": "Jeddah"}, _ctx())
    assert out["matched_location"] is True
    assert [b["name"] for b in out["branches"]] == ["Jeddah"]


def test_find_branch_matches_district():
    out = dispatch("find_branch", {"location": "Olaya"}, _ctx())
    assert [b["name"] for b in out["branches"]] == ["Olaya"]


def test_find_branch_prefers_service():
    # Riyadh has two branches; only Olaya offers Dental Checkup.
    out = dispatch("find_branch", {"location": "Riyadh", "service": "Dental Checkup"}, _ctx())
    names = [b["name"] for b in out["branches"]]
    assert names == ["Olaya"]


def test_find_branch_no_location_lists_all():
    out = dispatch("find_branch", {}, _ctx())
    assert out["total_branches"] == 3 and len(out["branches"]) == 3
    assert out["matched_location"] is False


def test_find_branch_when_single_location():
    out = dispatch("find_branch", {"location": "Riyadh"}, _ctx({"clinic": {"name": "Solo"}}))
    assert out["error"] == "no_branches"


def test_prompt_includes_branches_block():
    p = build_system_prompt(clinic_data=CLINIC)
    assert "MULTIPLE BRANCHES" in p and "find_branch" in p
    assert "Riyadh" in p and "Jeddah" in p


def test_prompt_no_branches_block_when_single_location():
    p = build_system_prompt(clinic_data={"clinic": {"name": "Solo"}})
    assert "MULTIPLE BRANCHES" not in p
