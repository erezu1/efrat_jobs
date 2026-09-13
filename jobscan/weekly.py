"""Weekly email: new positions from the past 7 days + deadlines in the next 14 days.

Usage:  python -m jobscan.weekly [--force] [--dry-run]

GitHub cron runs in UTC, so the workflow fires at two UTC hours and this script only sends when it
is 08:xx in Amsterdam (handles summer/winter time). --force skips that check.
Needs env: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO (comma-separated); optional SMTP_PORT, PAGE_URL.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import sys
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from .render import build_rows

ROOT = Path(__file__).resolve().parent.parent
MIN_SCORE = int(os.environ.get("WEEKLY_MIN_SCORE", "5"))
DEADLINE_DAYS = 14
CATS = {"phd": "PhD", "technician_research": "Technician / research",
        "conservation_zoo_ngo": "Conservation / zoo / NGO", "industry": "Industry", "other": "Other"}


def collect(state: dict, today: date) -> tuple[list[dict], list[tuple[int, dict]]]:
    rows = [r for r in build_rows(state)
            if r["pre"] and r["nl"] is not False and (r["score"] or 0) >= MIN_SCORE]
    week_ago = (today - timedelta(days=7)).isoformat()
    new = sorted((r for r in rows if (r["first_seen"] or "") > week_ago),
                 key=lambda r: (-(r["score"] or 0), r["deadline"] or "9999"))
    closing = []
    for r in rows:
        try:
            d = (date.fromisoformat(r["deadline"]) - today).days if r["deadline"] else None
        except ValueError:
            d = None
        if d is not None and 0 <= d <= DEADLINE_DAYS:
            closing.append((d, r))
    closing.sort(key=lambda x: (x[0], -(x[1]["score"] or 0)))
    return new, closing


def _meta(r: dict) -> str:
    bits = [r["org"], r["loc"], CATS.get(r["cat"], "")]
    if r["deadline"]:
        bits.append(f"deadline {r['deadline']}")
    return " · ".join(b for b in bits if b)


def build_email(new, closing, today: date) -> tuple[str, str, str]:
    page = os.environ.get("PAGE_URL", "")
    subject = f"Job scout — {len(new)} new position{'s' if len(new) != 1 else ''}, " \
              f"{len(closing)} deadline{'s' if len(closing) != 1 else ''} soon ({today:%d %b})"

    # plain text
    lines = [f"New positions this week ({len(new)})", ""]
    lines += [f"[{r['score']}/10] {r['title']}\n  {_meta(r)}\n  {r['url']}\n" for r in new] or ["None this week.", ""]
    lines += ["", f"Deadlines in the next {DEADLINE_DAYS} days ({len(closing)})", ""]
    lines += [f"{d} day{'s' if d != 1 else ''} left — [{r['score']}/10] {r['title']}\n  {_meta(r)}\n  {r['url']}\n"
              for d, r in closing] or ["None.", ""]
    if page:
        lines += ["", f"All jobs: {page}"]
    text = "\n".join(lines)

    # html
    e = html.escape

    def item(r, badge=""):
        summary = (f'<div style="color:#444;font-size:13px;margin-top:4px">{e(r["summary"][:180])}</div>'
                   if r["summary"] else "")
        return (f'<tr><td style="padding:10px 0;border-bottom:1px solid #eee;vertical-align:top;width:44px">'
                f'<div style="background:{"#1f6f5c" if r["score"] >= 7 else "#7a8f2a"};color:#fff;border-radius:8px;'
                f'width:36px;height:36px;line-height:36px;text-align:center;font-weight:700">{r["score"]}</div></td>'
                f'<td style="padding:10px 0 10px 10px;border-bottom:1px solid #eee">'
                f'{badge}<a href="{e(r["url"])}" style="color:#1d2320;font-weight:600;font-size:15px">{e(r["title"])}</a>'
                f'<div style="color:#667069;font-size:13px">{e(_meta(r))}</div>'
                f'{summary}</td></tr>')

    def dl_badge(d):
        col = "#b3261e" if d <= 7 else "#b4541a"
        return (f'<span style="background:{col};color:#fff;border-radius:5px;padding:1px 7px;font-size:12px;'
                f'margin-right:6px">{"today" if d == 0 else f"{d} day" + ("s" if d != 1 else "") + " left"}</span>')

    empty = '<p style="color:#667069">None this week.</p>'
    body = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:auto;color:#1d2320">
<h2 style="margin:0 0 4px">🧬 Weekly job scout</h2>
<div style="color:#667069;font-size:13px;margin-bottom:18px">Biology jobs in the Netherlands · week ending {today:%d %B %Y}</div>
<h3 style="margin:18px 0 4px">New positions this week ({len(new)})</h3>
{f'<table style="width:100%;border-collapse:collapse">{"".join(item(r) for r in new)}</table>' if new else empty}
<h3 style="margin:26px 0 4px">Deadlines in the next {DEADLINE_DAYS} days ({len(closing)})</h3>
{f'<table style="width:100%;border-collapse:collapse">{"".join(item(r, dl_badge(d)) for d, r in closing)}</table>' if closing else empty}
{f'<p style="margin-top:26px"><a href="{e(page)}" style="background:#1f6f5c;color:#fff;padding:9px 16px;border-radius:8px;text-decoration:none">Open all jobs</a></p>' if page else ""}
<p style="color:#98a29b;font-size:12px;margin-top:22px">Only jobs with a fit score of {MIN_SCORE}+ are listed.</p>
</div>"""
    return subject, text, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="send regardless of Amsterdam time")
    ap.add_argument("--dry-run", action="store_true", help="print instead of sending")
    args = ap.parse_args()

    now = datetime.now(ZoneInfo("Europe/Amsterdam"))
    if not args.force and not args.dry_run and now.hour != 8:
        print(f"Amsterdam time is {now:%H:%M}; weekly mail is sent at 08:xx — skipping.")
        return 0

    state = json.loads((ROOT / "data" / "jobs.json").read_text())
    new, closing = collect(state, now.date())
    subject, text, body = build_email(new, closing, now.date())
    if args.dry_run:
        print(subject, "\n", text, sep="")
        (ROOT / "data" / "weekly_preview.html").write_text(body)
        return 0

    host, user, pw, to = ((os.environ.get(k) or "").strip().strip("'\"")
                          for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
    pw = pw.replace(" ", "")   # Google shows app passwords in groups of 4 with spaces
    if not (host and user and pw and to):
        print("SMTP_HOST / SMTP_USER / SMTP_PASSWORD / EMAIL_TO not set — cannot send.", file=sys.stderr)
        return 1
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT") or "465")) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"weekly mail sent ({len(new)} new, {len(closing)} closing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
