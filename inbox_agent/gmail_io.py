"""Thin Gmail API wrapper for the inbox agent (the shared Grok/Claude inbox).

Setup once: create an OAuth "Desktop app" client in Google Cloud, enable the
Gmail API, save it as credentials.json next to this file, then run
`python agent.py --once`; a browser opens to sign in as the bridge inbox and token.json is saved.
"""
from __future__ import annotations

import base64
import html
import re
from email.mime.text import MIMEText
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
HERE = Path(__file__).parent
import os
TASK_ADDR = os.environ.get("KTASK_ADDRESS", "yourname+kalshi-task@gmail.com")
LABEL_DONE = "kalshi/done"
LABEL_REJECTED = "kalshi/rejected"


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    tok = HERE / "token.json"
    creds = Credentials.from_authorized_user_file(tok, SCOPES) if tok.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(HERE / "credentials.json", SCOPES).run_local_server(port=0)
        tok.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def label_id(svc, name: str) -> str:
    for l in svc.users().labels().list(userId="me").execute().get("labels", []):
        if l["name"] == name:
            return l["id"]
    return svc.users().labels().create(userId="me", body={"name": name}).execute()["id"]


def open_task_threads(svc, days: int = 7) -> list[str]:
    q = f'subject:KTASK newer_than:{days}d -label:{LABEL_DONE.replace("/", "-")} -label:{LABEL_REJECTED.replace("/", "-")}'
    res = svc.users().threads().list(userId="me", q=q, maxResults=50).execute()
    return [t["id"] for t in res.get("threads", [])]


def thread_messages(svc, thread_id: str) -> list[dict]:
    t = svc.users().threads().get(userId="me", id=thread_id, format="full").execute()
    out = []
    for m in t.get("messages", []):
        hdr = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
        out.append({"id": m["id"], "thread_id": thread_id, "subject": hdr.get("subject", ""),
                    "from": hdr.get("from", ""), "date": hdr.get("date", ""),
                    "internal_ms": int(m.get("internalDate", 0)), "text": _body_text(m["payload"])})
    return out


def _body_text(payload) -> str:
    plain, htm = [], []

    def walk(p):
        mt, data = p.get("mimeType", ""), p.get("body", {}).get("data")
        if data:
            txt = base64.urlsafe_b64decode(data + "==").decode("utf-8", "replace")
            (plain if mt == "text/plain" else htm if mt == "text/html" else []).append(txt)
        for c in p.get("parts", []) or []:
            walk(c)
    walk(payload)
    if plain:
        return "\n".join(plain)
    # html fallback: keep hrefs, drop tags
    s = "\n".join(htm)
    s = re.sub(r"(?i)<br\s*/?>|</div>|</p>", "\n", s)
    s = re.sub(r"(?is)<blockquote.*", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s)


def add_label(svc, thread_id: str, name: str) -> None:
    svc.users().threads().modify(userId="me", id=thread_id,
                                 body={"addLabelIds": [label_id(svc, name)]}).execute()


def send_task(svc, task_id: str, ticker: str, question: str, market: str, deadline: str) -> dict:
    body = (f"KTASK {task_id}\nMARKET: {ticker} - {market}\nQUESTION: {question}\nDEADLINE: {deadline}\n\n"
            "Please reply IN THIS EMAIL THREAD using exactly this format:\n\n"
            f"KTASK {task_id} RESULT\nSUMMARY: <2-4 sentences>\nEVIDENCE:\n- <post URL> : <one line>\n"
            "LEAN: yes | no | neutral\nCONFIDENCE: <0.0-1.0>\nFRESHNESS: <time of newest post used>\n\n"
            "Every claim needs a post link. Never invent posts or links. "
            "If nothing credible is found, use LEAN: neutral and CONFIDENCE: 0.")
    msg = MIMEText(body)
    msg["to"] = TASK_ADDR
    msg["subject"] = f"[KTASK {task_id}] {ticker}: {question[:80]}"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return svc.users().messages().send(userId="me", body={"raw": raw}).execute()
