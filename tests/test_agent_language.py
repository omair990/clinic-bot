"""Strong language guard at the agent level: when the model drifts to the wrong language,
run_agent asks it to rewrite the reply in the patient's language (Arabic in → Arabic out)."""
from app import agent
from app.llm import LLMResult


def _replies(monkeypatch, *texts):
    """Stub the LLM so each successive generate() call returns the next text (no tool calls)."""
    seq = iter(texts)

    def fake_generate(system, messages, tools):
        return LLMResult(text=next(seq))

    monkeypatch.setattr(agent, "generate", fake_generate)


def test_arabic_patient_english_reply_is_regenerated(monkeypatch):
    # First the model wrongly answers in English; the guard nudges and it rewrites in Arabic.
    _replies(monkeypatch, "We are open from 9 to 11.", "نحن مفتوحون من ٩ إلى ١١.")
    ctx = agent.run_agent(None, "966500000000", "متى تفتحون؟", history=[])
    assert ctx.reply == "نحن مفتوحون من ٩ إلى ١١."


def test_english_patient_arabic_reply_is_regenerated(monkeypatch):
    _replies(monkeypatch, "نحن مفتوحون من ٩ إلى ١١.", "We are open from 9 to 11.")
    ctx = agent.run_agent(None, "966500000000", "what are your hours?", history=[])
    assert ctx.reply == "We are open from 9 to 11."


def test_matching_language_is_not_regenerated(monkeypatch):
    # Only one reply is provided; if the guard tried to regenerate, the iterator would raise.
    _replies(monkeypatch, "We are open from 9 to 11.")
    ctx = agent.run_agent(None, "966500000000", "what are your hours?", history=[])
    assert ctx.reply == "We are open from 9 to 11."


def test_failed_rewrite_keeps_original(monkeypatch):
    # The rewrite still comes back in the wrong language → keep the original rather than loop.
    _replies(monkeypatch, "We are open from 9 to 11.", "Still English, sorry.")
    ctx = agent.run_agent(None, "966500000000", "متى تفتحون؟", history=[])
    assert ctx.reply == "We are open from 9 to 11."
