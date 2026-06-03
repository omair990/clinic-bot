"""Token accumulation onto the agent context (pure, no DB)."""
from app.tools import AgentContext


def test_add_usage_sums_across_calls():
    ctx = AgentContext(wa_user="u")
    ctx.add_usage({"input_tokens": 100, "output_tokens": 20})
    ctx.add_usage({"input_tokens": 250, "output_tokens": 30})
    assert ctx.input_tokens == 350
    assert ctx.output_tokens == 50


def test_add_usage_tolerates_missing_or_none():
    ctx = AgentContext(wa_user="u")
    ctx.add_usage(None)
    ctx.add_usage({})
    ctx.add_usage({"input_tokens": None, "output_tokens": 5})
    assert ctx.input_tokens == 0
    assert ctx.output_tokens == 5
