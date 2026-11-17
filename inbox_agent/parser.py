"""Parse a Grok KTASK reply email into a structured observation.

Format (see grok-email-bridge.md, section 1):

    KTASK 001 RESULT
    SUMMARY: ...
    EVIDENCE:
    - https://x.com/<handle>/status/<id> : one line
    LEAN: yes | no | neutral
    CONFIDENCE: 0.0-1.0
    FRESHNESS: newest post time
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field, asdict

FIELDS = ("SUMMARY", "EVIDENCE", "LEAN", "CONFIDENCE", "FRESHNESS")
LEANS = {"yes", "no", "neutral"}

_RESULT_RE = re.compile(r"KTASK\s+(\d+)\s+RESULT", re.I)
_FIELD_RE = re.compile(r"^\s*(%s)\s*:\s*" % "|".join(FIELDS), re.M | re.I)
_QUOTE_HEADER_RE = re.compile(r"^\s*On .{5,200}? wrote:\s*$", re.M | re.S)
_X_STATUS_RE = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d+)"
)
_EVIDENCE_LINE_RE = re.compile(r"^\s*[-*•]\s*(\S+)\s*(?::|-|—)?\s*(.*)$")


@dataclass
class Evidence:
    url: str
    handle: str | None
    status_id: str | None
    note: str
    exists: bool | None = None      # set by linkcheck
    trusted: bool = False           # set by trust.py
    trust_tier: str | None = None


@dataclass
class Observation:
    task_id: str
    summary: str
    lean: str
    confidence: float
    freshness: str
    evidence: list[Evidence] = field(default_factory=list)
    source: str = "grok-x"
    errors: list[str] = field(default_factory=list)
    accepted: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ParseError(ValueError):
    pass


def unwrap_url(url: str) -> str:
    """Undo Gmail's https://www.google.com/url?q=... link rewriting."""
    url = url.strip().rstrip(".,;)>").lstrip("<(")
    p = urllib.parse.urlparse(url)
    if p.netloc.endswith("google.com") and p.path == "/url":
        q = urllib.parse.parse_qs(p.query).get("q") or urllib.parse.parse_qs(p.query).get("url")
        if q:
            url = q[0]
    # drop tracking query (?s=20&t=...)
    p = urllib.parse.urlparse(url)
    if p.netloc.endswith(("x.com", "twitter.com")):
        url = urllib.parse.urlunparse(p._replace(query="", fragment=""))
    return url


def strip_quoted(text: str) -> str:
    """Remove the quoted original task (everything from 'On ... wrote:')."""
    m = _QUOTE_HEADER_RE.search(text)
    if m:
        text = text[: m.start()]
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))


def parse_reply(text: str) -> Observation:
    body = strip_quoted(text.replace("\r\n", "\n"))
    m = _RESULT_RE.search(body)
    if not m:
        raise ParseError("no 'KTASK <id> RESULT' header")
    task_id = m.group(1).zfill(3)
    body = body[m.end():]

    # split into fields
    parts: dict[str, str] = {}
    matches = list(_FIELD_RE.finditer(body))
    for i, fm in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts[fm.group(1).upper()] = body[fm.end():end].strip()

    errors = [f"missing {f}" for f in FIELDS if f not in parts]

    lean = parts.get("LEAN", "").split()[0].lower().strip(".") if parts.get("LEAN") else ""
    if lean not in LEANS:
        errors.append(f"bad LEAN {parts.get('LEAN')!r}")

    conf = 0.0
    cm = re.search(r"\d*\.?\d+", parts.get("CONFIDENCE", ""))
    if cm:
        conf = float(cm.group())
        if conf > 1 and conf <= 100:  # tolerate "85" or "85%"
            conf /= 100
    else:
        errors.append(f"bad CONFIDENCE {parts.get('CONFIDENCE')!r}")
    if not 0 <= conf <= 1:
        errors.append(f"CONFIDENCE out of range: {conf}")

    evidence: list[Evidence] = []
    for line in parts.get("EVIDENCE", "").splitlines():
        em = _EVIDENCE_LINE_RE.match(line)
        if not em or not em.group(1).lower().startswith(("http", "<http")):
            continue
        url = unwrap_url(em.group(1))
        xm = _X_STATUS_RE.match(url)
        evidence.append(Evidence(
            url=url,
            handle=xm.group(1) if xm else None,
            status_id=xm.group(2) if xm else None,
            note=em.group(2).strip(),
        ))

    return Observation(
        task_id=task_id,
        summary=" ".join(parts.get("SUMMARY", "").split()),
        lean=lean,
        confidence=conf,
        freshness=parts.get("FRESHNESS", "").splitlines()[0].strip() if parts.get("FRESHNESS") else "",
        evidence=evidence,
        errors=errors,
    )
