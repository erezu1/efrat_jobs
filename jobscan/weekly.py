"""Weekly email: new positions from the past 7 days + deadlines in the next 14 days.

Usage:  python -m jobscan.weekly [--force] [--dry-run]

GitHub cron runs in UTC, so the workflow fires at two UTC hours and this script only sends when it
is 08:xx in Amsterdam (handles summer/winter time). --force skips that check.
Needs env: SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO (comma-separated); optional SMTP_PORT, PAGE_URL.
"""
from __future__ import annotations

import argparse
import base64
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
HEADER = ROOT / "docs" / "icons" / "email-header.png"   # logo + wordmark, made by tools/make_email_header.py
MIN_SCORE = int(os.environ.get("WEEKLY_MIN_SCORE", "5"))
DEADLINE_DAYS = 14
CATS = {"phd": "PhD", "technician_research": "Research & lab",
        "conservation_zoo_ngo": "Nature & zoos", "industry": "Industry", "other": "Other"}


def collect(state: dict, today: date) -> tuple[list[dict], list[tuple[int, dict]]]:
    rows = [r for r in build_rows(state)
            if r["pre"] and r["nl"] is not False and (r["score"] or 0) >= MIN_SCORE]
    for r in rows:   # show English translations of Dutch ads
        r["title"] = r.get("title_en") or r["title"]
        r["summary"] = r.get("summary_en") or r["summary"]
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


def build_email(new, closing, today: date, header_src: str = "cid:biojobs-header") -> tuple[str, str, str]:
    page = os.environ.get("PAGE_URL", "")
    subject = f"BioJobs — {len(new)} new position{'s' if len(new) != 1 else ''}, " \
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

    # html — same look as the app: purple→pink brand, rounded white cards on a soft purple ground.
    # Email clients ignore most modern CSS, so this is table-based with inline styles
    # (gradients/shadows degrade to flat colors / borders where unsupported).
    e = html.escape
    PURPLE, PINK, INK, MUTED, GROUND, LINE, CHIP = "#7b2d8e", "#c2378a", "#241a28", "#6f6474", "#f7f3f8", "#ece3ef", "#f0e8f2"
    FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

    def pill(text, bg, fg):
        return (f'<span style="display:inline-block;background:{bg};color:{fg};border-radius:8px;'
                f'padding:2px 8px;font-size:12px;font-weight:600;margin:0 4px 4px 0">{e(text)}</span>')

    def card(r, days_left=None):
        score_bg = PURPLE if r["score"] >= 7 else PINK
        tags = ""
        if days_left is not None:
            label = "Deadline today" if days_left == 0 else f"{days_left} day{'s' if days_left != 1 else ''} left"
            tags += pill(label, "#b3261e" if days_left <= 7 else "#fbeadf", "#fff" if days_left <= 7 else "#b4541a")
        elif r["deadline"]:
            tags += pill(f"Deadline {r['deadline']}", "#fbeadf", "#b4541a")
        if r["cat"]:
            tags += pill(CATS.get(r["cat"], r["cat"]), CHIP, MUTED)
        where = " · ".join(x for x in (r["org"], r["loc"]) if x)
        summary = (f'<div style="color:#4a404e;font-size:13px;line-height:1.45;margin-top:6px">{e(r["summary"][:200])}</div>'
                   if r["summary"] else "")
        return f"""
<tr><td style="padding:0 0 12px">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid {LINE};border-radius:16px;box-shadow:0 1px 3px rgba(40,20,45,.10)">
  <tr>
   <td width="52" valign="top" style="padding:16px 0 16px 16px">
    <table role="presentation" width="44" height="44" cellpadding="0" cellspacing="0"><tr>
     <td width="44" height="44" align="center" valign="middle" style="width:44px;height:44px;border-radius:12px;background:{score_bg};color:#ffffff;font-family:{FONT};font-size:18px;font-weight:700;line-height:44px;text-align:center">{r["score"]}</td>
    </tr></table>
   </td>
   <td valign="top" style="padding:14px 16px 14px 12px;font-family:{FONT}">
    <a href="{e(r["url"])}" style="color:{INK};font-weight:650;font-size:15px;line-height:1.35;text-decoration:none">{e(r["title"])}</a>
    <div style="color:{MUTED};font-size:13px;margin:3px 0 7px">{e(where)}</div>
    {tags}{summary}
   </td>
  </tr>
 </table>
</td></tr>"""

    def section(title, count, cards_html):
        body = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cards_html}</table>'
                if count else f'<div style="color:{MUTED};font-size:14px;padding:4px 0 12px">Nothing this week.</div>')
        return (f'<div style="font-family:{FONT};font-size:17px;font-weight:700;color:{INK};margin:22px 0 10px">{title} '
                f'<span style="display:inline-block;background:{CHIP};color:{PURPLE};border-radius:999px;'
                f'padding:1px 9px;font-size:13px;vertical-align:2px">{count}</span></div>{body}')

    button = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:18px auto 6px"><tr>'
              f'<td style="border-radius:999px;background:{PURPLE};background-image:linear-gradient(135deg,{PURPLE},#d6409f)">'
              f'<a href="{e(page)}" style="display:inline-block;padding:11px 24px;color:#fff;font-family:{FONT};font-size:14px;font-weight:600;'
              f'text-decoration:none;border-radius:999px">Open BioJobs</a></td></tr></table>') if page else ""

    body = f"""<div style="background:{GROUND};padding:24px 12px;font-family:{FONT}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto">
 <tr><td style="padding:0 4px 6px">
  <a href="{e(page)}" style="text-decoration:none;display:inline-block"><img src="{e(header_src)}" width="189" height="44" alt="BioJobs" style="display:block;border:0;width:189px;height:44px"></a>
  <div style="font-size:13px;color:{MUTED};margin-top:6px">Your weekly update · {today:%d %B %Y}</div>
 </td></tr>
 <tr><td style="padding:0 4px">
  {section("New positions this week", len(new), "".join(card(r) for r in new))}
  {section(f"Deadlines in the next {DEADLINE_DAYS} days", len(closing), "".join(card(r, d) for d, r in closing))}
  {button}
  <div style="color:#a397a8;font-size:12px;text-align:center;margin-top:14px">Showing jobs with a fit score of {MIN_SCORE} or more.</div>
 </td></tr>
</table>
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
    if args.dry_run:
        data_uri = "data:image/png;base64," + base64.b64encode(HEADER.read_bytes()).decode()
        subject, text, body = build_email(new, closing, now.date(), header_src=data_uri)
        print(subject, "\n", text, sep="")
        (ROOT / "data" / "weekly_preview.html").write_text('<meta charset="utf-8">' + body)
        return 0
    subject, text, body = build_email(new, closing, now.date())

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
    # embed the header image in the message so it shows even when remote images are blocked
    msg.get_payload()[1].add_related(HEADER.read_bytes(), "image", "png", cid="<biojobs-header>")
    with smtplib.SMTP_SSL(host, int(os.environ.get("SMTP_PORT") or "465")) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"weekly mail sent ({len(new)} new, {len(closing)} closing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
