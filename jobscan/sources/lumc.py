"""LUMC (Leiden University Medical Center) — vacancies via its Recruitee ATS.

Public Recruitee API https://lumc11.recruitee.com/api/offers/ lists every open
offer with close_at (application deadline) but only a placeholder description;
the ad text lives on lumc.nl. The lumc.nl RSS feed (/rss/vacatures) gives the
lumc.nl URL and a teaser; it is joined to the API by the vacancy code in the
title/slug (e.g. "B.26.AB.EL.125" <-> "b-26-ab-el-125-...").
Mostly clinical/support jobs, but also research analysts, PhD candidates and
lab technicians. Dutch-language ads.

source_id = Recruitee offer id.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date
from ._nldate import find_deadline

NAME = "lumc"
API = "https://lumc11.recruitee.com/api/offers/"
RSS = "https://www.lumc.nl/rss/vacatures"
AMS = ZoneInfo("Europe/Amsterdam")

# Vacancy codes look like "B.26.AB.EL.125" or "C.26.JM.FvD.141".
_CODE_RE = re.compile(r"^\s*([A-Z]\.\d{2}(?:\.[A-Za-z]{1,4}){1,3}\.\d{1,4})\s+", re.I)



def _local_date(ts: str | None) -> str | None:
    """'2026-10-11 21:59:59 UTC' -> '2026-10-11' (Amsterdam local date)."""
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(AMS).date().isoformat()
    except ValueError:
        return iso_date(ts)


def _rss() -> dict[str, dict]:
    """Map normalized vacancy-code prefix of the lumc.nl slug -> {url, teaser}."""
    try:
        raw = get(RSS).content.decode("utf-8", errors="replace")  # declared utf-16, really utf-8
    except Exception:
        return {}
    out = {}
    for item in re.findall(r"<item[\s>].*?</item>", raw, re.S):
        link = re.search(r"<link>(.*?)</link>", item, re.S)
        desc = re.search(r"<description>(.*?)</description>", item, re.S)
        if not link:
            continue
        url = html.unescape(link.group(1).strip())
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        out[slug] = {"url": url, "teaser": html_to_text(html.unescape(desc.group(1)) if desc else "", 1500)}
    return out


def fetch() -> list[Job]:
    offers = get(API).json().get("offers", [])
    rss = _rss()
    jobs: dict[str, Job] = {}
    for o in offers:
        if o.get("status") not in (None, "published"):
            continue
        sid = str(o["id"])
        title = (o.get("title") or "").strip()
        m = _CODE_RE.match(title)
        code = m.group(1) if m else ""
        clean_title = title[m.end():].strip() if m else title
        url = o.get("careers_url") or ""
        teaser = ""
        if code:
            prefix = "-".join(code.lower().split(".")) + "-"
            for slug, info in rss.items():
                if slug.startswith(prefix):
                    url, teaser = info["url"], info["teaser"]
                    break
        hours = ""
        if o.get("min_hours") or o.get("max_hours"):
            hours = f"{o.get('min_hours')}-{o.get('max_hours')} uur/week"
        desc_bits = [teaser, f"Afdeling: {o['department']}" if o.get("department") else "", hours]
        jobs[sid] = Job(
            source=NAME,
            source_id=sid,
            url=url,
            title=clean_title,
            organization="LUMC" + (f" — {o['department'].strip(chr(0x200b)).strip()}" if o.get("department") else ""),
            location=o.get("city") or "Leiden",
            description="\n".join(b for b in desc_bits if b),
            deadline=_local_date(o.get("close_at")),
            posted=_local_date(o.get("published_at") or o.get("created_at")),
            extra={"code": code, "apply_url": o.get("careers_apply_url"),
                   "education": o.get("education_code"), "employment": o.get("employment_type_code")},
        )
    return list(jobs.values())


def enrich(job: Job) -> Job:
    if "lumc.nl" not in job.url:
        return job  # Recruitee page carries only a placeholder text
    time.sleep(1)
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    for tag in soup.select("script, style, nav, header, footer, form"):
        tag.decompose()
    full = html_to_text(str(soup.body or soup), 200000)
    # Ad body runs from the "Je hebt nog N dag(en)" line / intro to the footer ("Feedback").
    i = full.find("Je hebt nog")
    if i < 0:
        code = job.extra.get("code") or ""
        i = full.find(code) if code else -1
        if i < 0 and job.title:
            i = full.find(job.title)
    text = full[max(i, 0):]
    j = text.find("Feedback")
    if j > 0:
        text = text[:j]
    text = re.sub(r"(?m)^\s*(Deel deze pagina.*|Solliciteer nu)\s*$\n?", "", text).strip()[:8000]
    if len(text) > len(job.description or ""):
        job.description = text
    if not job.deadline:
        m = re.search(r"Je hebt nog (\d+) dag", text)
        if m:
            job.deadline = (datetime.now(AMS).date() + timedelta(days=int(m.group(1)))).isoformat()
        else:
            job.deadline = find_deadline(text)
    return job
