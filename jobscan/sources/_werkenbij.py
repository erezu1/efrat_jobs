"""Shared scraper for the "werkenbij" career-site platform used by
werkenbij.uva.nl and werkenbijumcutrecht.nl (same vendor: /api/token,
a.vacancy-item cards, ?n=<page size> and ?o=<offset> listing parameters).

The listing is server-rendered; `?n=1000` returns every vacancy on one page
(we still follow ?o= offsets defensively). Each card carries title, org unit,
salary, hours and the closing date ("Sluit op"/"Closes on" dd-mm-yyyy).
Detail pages embed a schema.org JobPosting (JSON-LD) with the full description.
"""
from __future__ import annotations

import json
import re
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date
from ._nldate import find_deadline, parse_date

PAGE_SIZE = 1000


def _cards(listing_url: str) -> list[dict]:
    out: dict[str, dict] = {}
    offset = 0
    while True:
        params = {"n": PAGE_SIZE}
        if offset:
            params["o"] = offset
        soup = BeautifulSoup(get(listing_url, params=params).text, "html.parser")
        cards = soup.select("a.vacancy-item[href]")
        new = 0
        for a in cards:
            href = a["href"].split("#")[0]
            m = re.search(r"-(\d+)/?$", href)
            if not m:
                continue
            vid = m.group(1)
            if vid in out:
                continue
            new += 1
            meta: dict[str, str] = {}
            deadline = None
            for li in a.select("ul.metadata li"):
                classes = [c for c in li.get("class", []) if c not in ("success-factors", "talentsoft")]
                key = classes[0] if classes else "other"
                if key == "end-date":
                    d = li.select_one(".date-metadata")
                    deadline = parse_date(d.get_text(" ", strip=True)) if d else None
                    if not deadline and d is not None and d.get("data-utc"):
                        deadline = iso_date(d["data-utc"])
                    continue
                meta[key] = " ".join(li.get_text(" ", strip=True).split())
            h3 = a.select_one(".vacancy-item-titles h3") or a.select_one("h3")
            summ = a.select_one(".vacancy-item-right .text") or a.select_one(".vacancy-item-body > .text")
            out[vid] = {
                "id": vid,
                "url": href,
                "title": h3.get_text(" ", strip=True) if h3 else "",
                "meta": meta,
                "deadline": deadline,
                "summary": summ.get_text(" ", strip=True) if summ else "",
            }
        if len(cards) < PAGE_SIZE or new == 0:
            break
        offset += PAGE_SIZE
    return list(out.values())


def fetch_jobs(source: str, org: str, location: str, listing_urls: list[str]) -> list[Job]:
    jobs: dict[str, Job] = {}
    for url in listing_urls:
        for c in _cards(url):
            if c["id"] in jobs:
                continue
            meta = c["meta"]
            unit = meta.get("location") or meta.get("custom-filter01") or ""
            info = "; ".join(v for k, v in meta.items() if k != "location")
            desc = c["summary"] + (f"\n{info}" if info else "")
            jobs[c["id"]] = Job(
                source=source,
                source_id=c["id"],
                url=c["url"],
                title=c["title"],
                organization=org + (f" — {unit}" if unit and meta.get("location") else ""),
                location=location,
                description=desc.strip(),
                deadline=c["deadline"],
                extra={k: v for k, v in meta.items()},
            )
    return list(jobs.values())


def enrich_job(job: Job) -> Job:
    time.sleep(1)
    page = get(job.url).text
    posting = None
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                posting = d
    text = ""
    if posting:
        text = html_to_text(posting.get("description"), 8000)
        if not job.posted:
            job.posted = iso_date(posting.get("datePosted"))
        loc = ((posting.get("jobLocation") or {}).get("address") or {}).get("addressLocality")
        if loc and not job.location:
            job.location = loc
    if not text:
        soup = BeautifulSoup(page, "html.parser")
        for tag in soup.select("script, style, nav, header, footer"):
            tag.decompose()
        text = html_to_text(str(soup.body or soup), 8000)
    if len(text) > len(job.description or ""):
        header = job.description.split("\n", 1)[1] if "\n" in (job.description or "") else ""
        job.description = ((header + "\n") if header else "") + text
        job.description = job.description[:8000]
    if not job.deadline:
        # Cards without a closing date are open-ended ads; JSON-LD validThrough
        # is then just a platform posting-expiry, so only trust explicit text.
        job.deadline = find_deadline(text)
    return job
