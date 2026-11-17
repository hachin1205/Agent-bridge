# Grok email bridge: setup

How the Kalshi platform and your Grok bot talk through your Gmail. The platform (or Claude) sends a task email; Grok replies in the same thread; the inbox agent reads the reply and posts it to the blackboard.

## 1. Message format

**Task email (platform to Grok)**

- To: your Gmail with a plus tag, e.g. `yourname+kalshi-task@gmail.com`
- Subject: `[KTASK 001] <market ticker>: <short question>`
- Body:

```
KTASK 001
MARKET: <Kalshi ticker and title>
QUESTION: What are credible X accounts saying about this in the last 2 hours?
DEADLINE: 2026-11-16 18:00 ET
REPLY FORMAT: see below
```

**Grok's reply (same thread, subject starts with `Re: [KTASK 001]`)**

```
KTASK 001 RESULT
SUMMARY: 2-4 sentences on what X is saying.
EVIDENCE:
- https://x.com/... : one line on what this post says
- https://x.com/... : ...
LEAN: yes | no | neutral
CONFIDENCE: 0.0-1.0
FRESHNESS: newest post time
```

Rules: every claim needs a post link; no link means the inbox agent rejects it. "Nothing credible found" is a valid answer (LEAN: neutral, CONFIDENCE: 0).

## 2. Instructions to paste into Grok

Paste this as Grok's standing instruction, as a custom instruction, a scheduled Task, or the first message of a dedicated chat:

```
You are the X research agent for my Kalshi trading system.
When I give you a KTASK (or when you find unanswered emails with subject
starting "[KTASK"), search X for the question asked, focusing on the last
few hours and on credible accounts (reporters, officials, primary sources).
Ignore engagement bait and unverified rumors unless many credible accounts
repeat them. Answer ONLY in this format:

KTASK <id> RESULT
SUMMARY: <2-4 sentences>
EVIDENCE:
- <post URL> : <one line>
LEAN: yes | no | neutral
CONFIDENCE: <0.0-1.0>
FRESHNESS: <time of newest post used>

Never invent posts or links. If you find nothing credible, say so with
LEAN: neutral and CONFIDENCE: 0.
```

## 3. Gmail setup (one time)

1. Create a Gmail filter: To `yourname+kalshi-task@gmail.com` → apply label `kalshi/tasks`, skip inbox.
2. Create label `kalshi/done`. The inbox agent moves handled threads there.

## 4. How Grok gets the task (pick what your Grok can do)

| Grok can... | Flow |
| --- | --- |
| Read and send Gmail itself | Fully automatic: Grok checks `label:kalshi/tasks` on a schedule and replies in the thread. |
| Not touch Gmail | Semi-manual: you paste the task email into your Grok chat and paste Grok's answer as a reply to the task email. The inbox agent takes it from there. |

## 5. Test

1. Claude sends one test task, `[KTASK 000] TEST`, to your plus address.
2. You (or Grok) reply in the format above.
3. Claude reads the reply and shows the observation it parsed.

## Status

Tested end to end on 2026-11-16: a `[KTASK 001]` task sent from the bridge inbox to its `+kalshi-task` address got a Grok reply in the same thread, and the reply parsed into all fields (see `inbox_agent/tests/fixtures/ktask001_reply.txt`).
