"""Check that each evidence link points at a real, public X post.

Uses X's public oEmbed endpoint (no API key): it returns 200 with the
post's author for a live public post, and 404 for a deleted, private or
made-up one. We also confirm the author handle matches the URL, so a link
Grok invented with a real status id under the wrong account is caught.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

OEMBED = "https://publish.twitter.com/oembed?omit_script=1&url="
UA = "kalshi-inbox-agent/0.1"


def check_post(url: str, handle: str | None, timeout: float = 10.0) -> tuple[bool | None, str]:
    """Return (exists, reason). exists=None means we couldn't tell (network/rate limit)."""
    if handle is None:
        return False, "not an x.com status link"
    req = urllib.request.Request(OEMBED + urllib.parse.quote(url, safe=""), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return False, f"post not found ({e.code})"
        return None, f"http {e.code}"
    except Exception as e:  # network, timeout
        return None, f"error: {e.__class__.__name__}"
    author = (data.get("author_url") or "").rstrip("/").rsplit("/", 1)[-1]
    if author and author.lower() != handle.lower():
        return False, f"author mismatch: post is by @{author}"
    return True, "ok"


def check_all(obs, delay: float = 0.5) -> None:
    for ev in obs.evidence:
        ev.exists, reason = check_post(ev.url, ev.handle)
        if ev.exists is False:
            obs.errors.append(f"dead link {ev.url}: {reason}")
        elif ev.exists is None:
            obs.errors.append(f"unverified link {ev.url}: {reason}")
        time.sleep(delay)
