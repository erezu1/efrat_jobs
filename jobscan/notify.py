"""Daily digest of new good matches and approaching deadlines.

Always writes data/digest.md (empty file when there is nothing to report; the GitHub
workflow turns a non-empty digest into an issue, which GitHub emails to repo watchers).
Also emails it if SMTP_HOST, SMTP_USER, SMTP_PASSWORD and EMAIL_TO are set.
"""
from __future__ import annotations

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from .render import build_rows

ROOT = Path(__file__).resolve().parent.parent
MIN_SCORE = int(os.environ.get("DIGEST_MIN_SCORE", "6"))
REMIND_DAYS = {7, 3, 1}


def _line(r: dict, extra: str = "") -> str:
    s = r["score"] if r["score"] is not None else "?"
    dl = f" — deadline {r['deadline']}" if r.get("deadline") else ""
    summary = f"\n  {r['summary']}" if r.get("summary") else ""
    return f"- **[{s}/10] [{r['title']}]({r['url']})** — {r['org']}{dl}{extra}{summary}"


def build_digest(state: dict, today: str) -> str:
    rows = [r for r in build_rows(state) if r["pre"] and r["nl"] is not False]
    good = [r for r in rows if r["score"] is None or r["score"] >= MIN_SCORE]
    new = sorted((r for r in good if r["first_seen"] == today),
                 key=lambda r: -(r["score"] or 0))
    t = date.fromisoformat(today)
    closing = []
    for r in good:
        if r.get("deadline"):
            try:
                d = (date.fromisoformat(r["deadline"]) - t).days
            except ValueError:
                continue
            if d in REMIND_DAYS and r["first_seen"] != today:
                closing.append((d, r))
    closing.sort(key=lambda x: x[0])
    if not new and not closing:
        return ""
    parts = []
    if new:
        parts.append(f"## 🆕 {len(new)} new match{'es' if len(new) != 1 else ''}\n")
        parts += [_line(r) for r in new]
    if closing:
        parts.append(f"\n## ⏰ Deadlines coming up\n")
        parts += [_line(r, f" (**{d} day{'s' if d != 1 else ''} left**)") for d, r in closing]
    page = os.environ.get("PAGE_URL")
    if page:
        parts.append(f"\nFull list: {page}")
    return "\n".join(parts) + "\n"


def notify(state: dict, today: str) -> None:
    digest = build_digest(state, today)
    (ROOT / "data" / "digest.md").write_text(digest)
    if not digest:
        print("digest: nothing new")
        return
    print(digest)
    host, user, pw, to = (os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
    if not (host and user and pw and to):
        return
    msg = EmailMessage()
    msg["Subject"] = f"Job scout {today}: new biology jobs in NL"
    msg["From"] = user
    msg["To"] = to
    msg.set_content(digest)
    with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT", "465"))) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"digest emailed to {to}")
