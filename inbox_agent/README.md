# Grok inbox agent

Reads Grok's `Re: [KTASK nnn]` replies in the bridge Gmail inbox, checks them, and posts each one as an observation to the blackboard. Without a blackboard yet, observations go to `observations.jsonl`.

## Pipeline

1. **Find** (`gmail_io.py`): KTASK threads from the last 7 days that have no `kalshi/done` or `kalshi/rejected` label yet.
2. **Parse** (`parser.py`): reads the latest reply. Cuts off the quoted task, unwraps Gmail's `google.com/url?q=` links, and fills in task_id, summary, evidence, lean, confidence and freshness.
3. **Link check** (`linkcheck.py`): asks X's public oEmbed endpoint whether each post exists, and checks that the post's author matches the handle in the URL. Invented links fail here.
4. **Trust** (`trust.py` + `trusted_accounts.json`):
   - Format errors: rejected.
   - "Nothing credible found" (neutral, 0): accepted.
   - More than half the links dead: rejected as likely invented. A minority of dead links is dropped.
   - No link confirmed live: rejected.
   - No primary or reporter source: confidence capped at 0.4. Analyst sources only: capped at 0.7.
5. **Publish** (`agent.py`): POSTs to `$BLACKBOARD_URL/observations`, or appends to `observations.jsonl`. Then labels the thread `kalshi/done` or `kalshi/rejected`.

The decision agent should use `effective_confidence`, not Grok's raw `confidence`.

## Run

```
pip install -r requirements.txt
# Google Cloud: enable the Gmail API, create an OAuth "Desktop app" client, save it as credentials.json here
export KTASK_ADDRESS=yourname+kalshi-task@gmail.com
python agent.py --once                     # first run opens a browser to sign in to the bridge inbox
python agent.py --every 120                # poll every 2 min
python agent.py --parse-file tests/fixtures/ktask001_reply.txt   # offline check
python agent.py --send 002 KXFED-26DEC "Will the Fed cut in December?" "Fed Dec decision" "2026-11-17 18:00 ET"
pytest -q tests
```

## Edit the trust list

`trusted_accounts.json` starts with officials, wire services and a few named reporters. The 5 handles Grok cited for KTASK 001 are under `_suggested_by_grok_unreviewed`. Move any you trust into `accounts`.

## Known limits

- The link check needs to reach publish.twitter.com. It's blocked in the Claude cloud sandbox, so it has only been unit-tested there. On a normal computer it works as is. If X rate-limits it, the links count as "unverified", which ends in rejection.
- No secrets are in this folder. `credentials.json` and `token.json` are created locally and must not be committed.
