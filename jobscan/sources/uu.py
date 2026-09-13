"""Utrecht University — own vacancy pages on uu.nl (Drupal, server-rendered).

The Dutch listing is a superset: it shows every vacancy (English-only ads link to
their /en/ page, Dutch-language ads — often support/technician jobs — link to
/organisatie/...). The English listing shows only ads that have an English
version. Both listings are unpaginated (all items in one page) and carry the
application deadline as <time datetime=...>.

source_id = URL slug of the link on the Dutch listing (stable). When a Dutch ad
also has an English version, the English URL/title is used for display.
"""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date
from ._nldate import find_deadline, parse_date

NAME = "uu"
BASE = "https://www.uu.nl"
LIST_NL = BASE + "/organisatie/werken-bij-de-universiteit-utrecht/vacatures"
LIST_EN = BASE + "/en/organisation/working-at-utrecht-university/jobs"


def _parse_listing(url: str) -> list[dict]:
    soup = BeautifulSoup(get(url).text, "html.parser")
    out = []
    for li in soup.select("li.overview-list__item"):
        box = li.select_one(".vacancy") or li
        a = box.select_one("h3 a[href]")
        if not a:
            continue
        href = a["href"]
        meta = {}
        for dt in box.select("dl dt"):
            dd = dt.find_next_sibling("dd")
            if dd:
                meta[dt.get_text(strip=True).rstrip(":\xa0 ").lower()] = dd
        deadline = None
        for key, dd in meta.items():
            if "deadline" in key or "sluitingsdatum" in key or "reageren" in key:
                t = dd.find("time")
                deadline = iso_date(t.get("datetime")) if t and t.get("datetime") else parse_date(dd.get_text(" "))
        summary = box.select_one(".list-item__main p")
        pos = box.select_one(".position")
        fac = box.select_one(".department")
        dept = next((dd.get_text(" ", strip=True) for k, dd in meta.items()
                     if k.startswith("department") or k.startswith("afdeling")), "")
        out.append({
            "href": href,
            "slug": href.rstrip("/").rsplit("/", 1)[-1],
            "title": a.get_text(" ", strip=True),
            "summary": summary.get_text(" ", strip=True) if summary else "",
            "position": pos.get_text(" ", strip=True) if pos else "",
            "faculty": fac.get_text(" ", strip=True) if fac else "",
            "department": dept,
            "deadline": deadline,
            "lang": "en" if href.startswith("/en/") else "nl",
        })
    return out


def _nl_twin(en_href: str) -> str | None:
    """Path of the Dutch version of an English ad (from its hreflang links), if any."""
    try:
        page = get(BASE + en_href).text
    except Exception:
        return None
    m = re.search(r'hreflang="nl" href="https://www\.uu\.nl(/[^"]+)"', page)
    return m.group(1) if m else None


def fetch() -> list[Job]:
    nl = _parse_listing(LIST_NL)
    try:
        en = _parse_listing(LIST_EN)
    except Exception:
        en = []
    nl_by_href = {n["href"]: n for n in nl}
    # English ads that the Dutch listing shows in their Dutch version (usually 0-5):
    # one cheap request each to read the hreflang link to the Dutch twin.
    english_of: dict[str, dict] = {}
    extra: list[dict] = []
    for e in en:
        if e["href"] in nl_by_href:
            continue
        time.sleep(0.5)
        twin = _nl_twin(e["href"])
        if twin and twin in nl_by_href:
            english_of[twin] = e
        else:
            extra.append(e)

    jobs: dict[str, Job] = {}
    for it in nl + extra:
        sid = it["slug"]
        if sid in jobs:
            continue
        shown = english_of.get(it["href"], it)
        org = "Utrecht University" + (f" — {shown['faculty']}" if shown["faculty"] else "")
        if shown["department"]:
            org += f", {shown['department']}"
        jobs[sid] = Job(
            source=NAME,
            source_id=sid,
            url=BASE + shown["href"],
            title=shown["title"],
            organization=org,
            location="Utrecht",
            description=shown["summary"],
            deadline=it["deadline"] or shown["deadline"],
            extra={"position": shown["position"], "language": shown["lang"]},
        )
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(1)
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    for tag in soup.select("script, style, nav, header, footer, .social-share-links, .hs_applybutton"):
        tag.decompose()
    main = soup.select_one("main") or soup.body or soup
    head = main.select_one("dl")
    blocks = main.select(".content-block-vacancy")
    body = "\n".join(str(b) for b in blocks) if blocks else str(main)
    text = html_to_text(body, 8000)
    if head:
        text = html_to_text(str(head), 1000) + "\n" + text
    if len(text) > len(job.description or ""):
        job.description = text[:8000]
    if not job.deadline:
        t = main.select_one("dl time[datetime]")
        job.deadline = iso_date(t["datetime"]) if t else find_deadline(text)
    return job
