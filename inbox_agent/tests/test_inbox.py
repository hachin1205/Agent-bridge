import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parser import parse_reply, unwrap_url, ParseError  # noqa: E402
from trust import judge  # noqa: E402
import pytest  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "ktask001_reply.txt"
TRUSTED = {"reuters": {"tier": "reporter"}, "nicktimiraos": {"tier": "reporter"}, "natesilver538": {"tier": "analyst"}}


def test_parses_real_ktask001():
    o = parse_reply(FIX.read_text())
    assert o.task_id == "001" and o.lean == "no" and o.confidence == 0.85
    assert len(o.evidence) == 5 and o.evidence[0].handle == "DataDayPosts"
    assert o.freshness.startswith("2026-11-16 21:16 UTC")
    assert "Warsh" in o.summary and "<2-4" not in o.summary  # quoted template ignored
    assert o.errors == []


def test_unwrap_gmail_link():
    u = "https://www.google.com/url?q=https://x.com/Reuters/status/123?s%3D20&sa=D"
    assert unwrap_url(u) == "https://x.com/Reuters/status/123"


def _obs(handles, exists, conf=0.8):
    lines = "\n".join(f"- https://x.com/{h}/status/{i} : note" for i, h in enumerate(handles))
    o = parse_reply(f"KTASK 7 RESULT\nSUMMARY: s\nEVIDENCE:\n{lines}\nLEAN: yes\nCONFIDENCE: {conf}\nFRESHNESS: now")
    for e, x in zip(o.evidence, exists):
        e.exists = x
    return o


def test_untrusted_sources_capped():
    o = _obs(["randoguy", "other"], [True, True]); judge(o, TRUSTED)
    assert o.accepted and o.effective_confidence == 0.4


def test_trusted_source_keeps_confidence():
    o = _obs(["Reuters", "randoguy"], [True, True]); judge(o, TRUSTED)
    assert o.accepted and o.effective_confidence == 0.8 and o.evidence[0].trust_tier == "reporter"


def test_analyst_only_capped():
    o = _obs(["NateSilver538"], [True], conf=0.9); judge(o, TRUSTED)
    assert o.accepted and o.effective_confidence == 0.7


def test_mostly_dead_links_rejected():
    o = _obs(["Reuters", "a", "b"], [True, False, False]); judge(o, TRUSTED, links_checked=True)
    assert not o.accepted and "invented" in o.verdict


def test_dead_link_dropped_when_minority():
    o = _obs(["Reuters", "a", "b"], [True, True, False]); judge(o, TRUSTED, links_checked=True)
    assert o.accepted and len(o.evidence) == 2


def test_no_live_links_rejected():
    o = _obs(["Reuters"], [None]); judge(o, TRUSTED, links_checked=True)
    assert not o.accepted


def test_links_trusted_by_default():
    o = _obs(["randoguy", "other"], [None, None]); judge(o, TRUSTED)
    assert o.accepted and o.effective_confidence == 0.4 and len(o.evidence) == 2


def test_agent_does_not_fetch_by_default(monkeypatch):
    import agent
    monkeypatch.delenv("KTASK_LINKCHECK", raising=False)
    monkeypatch.setattr(agent, "check_all", lambda obs: pytest.fail("link check ran"))
    rec = agent.process_text(FIX.read_text())
    assert rec["accepted"] and rec["effective_confidence"] == 0.4


def test_agent_linkcheck_opt_in_env(monkeypatch):
    import agent
    called = []
    def fake(obs):
        called.append(1)
        for e in obs.evidence:
            e.exists = True
    monkeypatch.setenv("KTASK_LINKCHECK", "1")
    monkeypatch.setattr(agent, "check_all", fake)
    rec = agent.process_text(FIX.read_text())
    assert called and rec["accepted"]


def test_nothing_found_is_valid():
    o = parse_reply("KTASK 9 RESULT\nSUMMARY: nothing credible\nEVIDENCE:\nLEAN: neutral\nCONFIDENCE: 0\nFRESHNESS: n/a")
    judge(o, TRUSTED)
    assert o.accepted and o.task_id == "009"


def test_missing_field_rejected():
    o = parse_reply("KTASK 9 RESULT\nSUMMARY: x\nLEAN: maybe\nCONFIDENCE: 0.5")
    judge(o, TRUSTED)
    assert not o.accepted and any("LEAN" in e for e in o.errors)


def test_no_header_raises():
    with pytest.raises(ParseError):
        parse_reply("hello")
