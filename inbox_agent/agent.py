"""Inbox agent: turn Grok's KTASK replies into blackboard observations.

    python agent.py --once              # one pass over open KTASK threads
    python agent.py --every 120         # poll every 2 minutes
    python agent.py --parse-file r.txt  # offline: parse + check one reply
    python agent.py --send 002 KXFED-26DEC "Will the Fed cut in Dec?" "Fed Dec decision" "2026-11-17 18:00 ET"

Grok's links are trusted as given: the agent does not contact X unless you
opt in with --linkcheck or KTASK_LINKCHECK=1.

Output goes to BLACKBOARD_URL (POST /observations) if set, otherwise it is
appended to observations.jsonl next to this file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from linkcheck import check_all
from parser import ParseError, parse_reply
from trust import judge

HERE = Path(__file__).parent
OUT = HERE / "observations.jsonl"


def linkcheck_enabled() -> bool:
    return os.environ.get("KTASK_LINKCHECK", "").strip().lower() in ("1", "true", "yes", "on")


def process_text(text: str, meta: dict | None = None, check_links: bool | None = None):
    if check_links is None:
        check_links = linkcheck_enabled()
    obs = parse_reply(text)
    if check_links:
        check_all(obs)
    judge(obs, links_checked=check_links)
    d = obs.to_dict()
    d.update(effective_confidence=obs.effective_confidence, verdict=obs.verdict,
             received_at=datetime.now(timezone.utc).isoformat(), email=meta or {})
    return d


def publish(record: dict) -> None:
    url = os.environ.get("BLACKBOARD_URL")
    if url:
        req = urllib.request.Request(url.rstrip("/") + "/observations", method="POST",
                                     data=json.dumps(record).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    else:
        with OUT.open("a") as f:
            f.write(json.dumps(record) + "\n")


def run_once(svc, check_links: bool | None = None) -> int:
    import gmail_io as g
    n = 0
    for tid in g.open_task_threads(svc):
        msgs = g.thread_messages(svc, tid)
        replies = [m for m in msgs if "RESULT" in m["text"] and m["subject"].lower().startswith("re:")]
        if not replies:
            continue  # Grok hasn't answered yet
        latest = max(replies, key=lambda m: m["internal_ms"])
        meta = {k: latest[k] for k in ("id", "thread_id", "subject", "date")}
        try:
            rec = process_text(latest["text"], meta, check_links)
        except ParseError as e:
            rec = {"accepted": False, "verdict": f"unparseable: {e}", "email": meta}
        publish(rec)
        g.add_label(svc, tid, g.LABEL_DONE if rec["accepted"] else g.LABEL_REJECTED)
        print(f"[{meta['subject']}] -> {rec['verdict']}", file=sys.stderr)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int)
    ap.add_argument("--parse-file")
    ap.add_argument("--linkcheck", action="store_true",
                    help="verify each X link via oEmbed (off by default; or set KTASK_LINKCHECK=1)")
    ap.add_argument("--send", nargs=5, metavar=("ID", "TICKER", "QUESTION", "MARKET", "DEADLINE"))
    a = ap.parse_args()
    check_links = a.linkcheck or linkcheck_enabled()

    if a.parse_file:
        print(json.dumps(process_text(Path(a.parse_file).read_text(), check_links=check_links), indent=2))
        return
    import gmail_io as g
    svc = g.service()
    if a.send:
        print(g.send_task(svc, *a.send))
        return
    while True:
        run_once(svc, check_links)
        if not a.every:
            break
        time.sleep(a.every)


if __name__ == "__main__":
    main()
