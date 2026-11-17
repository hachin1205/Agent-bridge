"""Decide whether a parsed observation is accepted, and how much weight it gets.

Rules (all tunable in RULES):
1. Format errors (missing field, bad LEAN/CONFIDENCE) -> rejected.
2. "Nothing credible found" (LEAN neutral, CONFIDENCE 0) is accepted with no links.
3. Otherwise at least one evidence link must be confirmed live.
4. If more than half of the links are dead, the whole reply is rejected
   (Grok probably invented them).
5. If no live link is from a trusted account, confidence is capped at
   RULES["untrusted_conf_cap"].
"""
from __future__ import annotations

import json
from pathlib import Path

RULES = {
    "max_dead_fraction": 0.5,
    "untrusted_conf_cap": 0.4,
    "analyst_conf_cap": 0.7,     # only analysts, no primary/reporter source
}

DEFAULT_PATH = Path(__file__).with_name("trusted_accounts.json")
FORMAT_ERRORS = ("missing ", "bad LEAN", "bad CONFIDENCE", "CONFIDENCE out of range")


def load_trusted(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    data = json.loads(Path(path).read_text())
    return {h.lower(): v for h, v in data["accounts"].items()}


def judge(obs, trusted: dict[str, dict] | None = None) -> None:
    """Mutates obs: sets evidence trust fields, obs.accepted, obs.effective_confidence, obs.verdict."""
    trusted = trusted if trusted is not None else load_trusted()
    for ev in obs.evidence:
        info = trusted.get((ev.handle or "").lower())
        ev.trusted = info is not None
        ev.trust_tier = info["tier"] if info else "unknown"

    obs.effective_confidence = obs.confidence
    if any(e.startswith(FORMAT_ERRORS) for e in obs.errors):
        return _reject(obs, "format errors")

    if obs.lean == "neutral" and obs.confidence == 0:
        obs.accepted, obs.verdict = True, "nothing credible found"
        return

    if not obs.evidence:
        return _reject(obs, "no evidence links")

    dead = [e for e in obs.evidence if e.exists is False]
    live = [e for e in obs.evidence if e.exists is True]
    if len(dead) / len(obs.evidence) > RULES["max_dead_fraction"]:
        return _reject(obs, f"{len(dead)}/{len(obs.evidence)} links dead, likely invented")
    if not live:
        return _reject(obs, "no link could be confirmed live")

    tiers = {e.trust_tier for e in live}
    if tiers & {"primary", "reporter"}:
        verdict = "trusted sources"
    elif "analyst" in tiers:
        obs.effective_confidence = min(obs.confidence, RULES["analyst_conf_cap"])
        verdict = "analyst sources only, confidence capped"
    else:
        obs.effective_confidence = min(obs.confidence, RULES["untrusted_conf_cap"])
        verdict = "no trusted sources, confidence capped"
    obs.evidence = [e for e in obs.evidence if e.exists is not False]  # drop dead links
    obs.accepted, obs.verdict = True, verdict


def _reject(obs, why: str) -> None:
    obs.accepted, obs.verdict, obs.effective_confidence = False, why, 0.0
