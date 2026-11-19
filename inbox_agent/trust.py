"""Decide whether a parsed observation is accepted, and how much weight it gets.

Rules (all tunable in RULES):
1. Format errors (missing field, bad LEAN/CONFIDENCE) -> rejected.
2. "Nothing credible found" (LEAN neutral, CONFIDENCE 0) is accepted with no links.
3. Only when the optional link check ran (links_checked=True):
   at least one evidence link must be confirmed live, and if more than
   half of the links are dead the whole reply is rejected (Grok probably
   invented them). By default links are trusted as given.
5. Grok's CONFIDENCE is used as is. Each link is still tagged with its
   trust tier from trusted_accounts.json, for information only.
"""
from __future__ import annotations

import json
from pathlib import Path

RULES = {
    "max_dead_fraction": 0.5,
}

DEFAULT_PATH = Path(__file__).with_name("trusted_accounts.json")
FORMAT_ERRORS = ("missing ", "bad LEAN", "bad CONFIDENCE", "CONFIDENCE out of range")


def load_trusted(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    data = json.loads(Path(path).read_text())
    return {h.lower(): v for h, v in data["accounts"].items()}


def judge(obs, trusted: dict[str, dict] | None = None, links_checked: bool = False) -> None:
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

    if links_checked:
        dead = [e for e in obs.evidence if e.exists is False]
        live = [e for e in obs.evidence if e.exists is True]
        if len(dead) / len(obs.evidence) > RULES["max_dead_fraction"]:
            return _reject(obs, f"{len(dead)}/{len(obs.evidence)} links dead, likely invented")
        if not live:
            return _reject(obs, "no link could be confirmed live")
    else:
        live = obs.evidence  # Grok's links trusted as given

    tiers = {e.trust_tier for e in live}
    if tiers & {"primary", "reporter"}:
        verdict = "trusted sources"
    elif "analyst" in tiers:
        verdict = "analyst sources only"
    else:
        verdict = "no listed sources"
    obs.evidence = [e for e in obs.evidence if e.exists is not False]  # drop dead links
    obs.accepted, obs.verdict = True, verdict


def _reject(obs, why: str) -> None:
    obs.accepted, obs.verdict, obs.effective_confidence = False, why, 0.0
