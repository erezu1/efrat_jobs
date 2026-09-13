"""Wageningen University & Research — own vacancy site (wur.nl, Next.js).

Covers the university chair groups plus the Wageningen Research institutes
(Marine, Livestock, Bioveterinary, Environmental Research, Plant Research, ...),
including technician/support roles that are often not on AcademicTransfer.

The listing page embeds all current vacancies in its React Server Component
payload (self.__next_f.push chunks), so fetch() is one request per language.
The detail page carries a schema.org JobPosting (location, validThrough) and
server-rendered body text, which enrich() uses.
"""
from __future__ import annotations

import json
import re
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date

NAME = "wur"
BASE = "https://www.wur.nl"
LISTINGS = [
    BASE + "/en/jobs/jobs-wageningen-university-research",
    BASE + "/nl/werken-bij/vacatures-bij-wageningen-university-research",
]

_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def _rsc_payload(page: str) -> str:
    """Concatenate the decoded Next.js flight chunks embedded in the HTML."""
    out = []
    for m in _PUSH_RE.finditer(page):
        try:
            out.append(json.loads('"' + m.group(1) + '"'))
        except json.JSONDecodeError:
            continue
    return "".join(out)


def _listing_results(payload: str) -> list[dict]:
    i = payload.find('"numberOfItemsPerPage"')
    if i < 0:
        return []
    j = payload.find('"results":', i)
    if j < 0:
        return []
    try:
        results, _ = json.JSONDecoder().raw_decode(payload[j + len('"results":'):])
    except json.JSONDecodeError:
        return []
    return [r for r in results if isinstance(r, dict)]


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for url in LISTINGS:
        payload = _rsc_payload(get(url).text)
        for r in _listing_results(payload):
            gtm = r.get("gtm") or {}
            if gtm.get("contentType") not in (None, "Vacancy"):
                continue
            sid = str(r.get("id") or gtm.get("pageId") or r.get("path"))
            if not sid or sid in jobs:
                continue
            crit = {}
            for c in r.get("filterCriteria") or []:
                crit.setdefault(c.get("label", ""), []).append(c.get("value", ""))
            dept = gtm.get("department") or ""
            summary = html_to_text(r.get("summary") or "", 1500)
            meta = "; ".join(f"{k}: {', '.join(v)}" for k, v in crit.items() if k)
            jobs[sid] = Job(
                source=NAME,
                source_id=sid,
                url=BASE + (r.get("path") or ""),
                title=(r.get("title") or "").strip(),
                organization="Wageningen University & Research" + (f" — {dept}" if dept else ""),
                location="",
                description="\n".join(filter(None, [summary, meta])),
                deadline=iso_date(r.get("endDate") or gtm.get("vacancyEndDate")),
                posted=iso_date(gtm.get("createdDate")),
                extra={"department": dept, "language": r.get("language"), **crit},
            )
    return list(jobs.values())


def _job_posting(payload: str) -> dict | None:
    i = payload.find('"JobPosting"')
    if i < 0:
        return None
    ctx = payload.rfind('"@context"', 0, i)
    start = payload.rfind("{", 0, ctx if ctx >= 0 else i)
    try:
        obj, _ = json.JSONDecoder().raw_decode(payload[start:])
    except (json.JSONDecodeError, ValueError):
        return None
    for node in obj.get("@graph", [obj]) if isinstance(obj, dict) else []:
        if isinstance(node, dict) and node.get("@type") == "JobPosting":
            return node
    return None


def enrich(job: Job) -> Job:
    time.sleep(0.5)
    page = get(job.url).text
    payload = _rsc_payload(page)

    posting = _job_posting(payload)
    if posting:
        if not job.deadline:
            job.deadline = iso_date(posting.get("validThrough"))
        if not job.posted:
            job.posted = iso_date(posting.get("datePosted"))
        locs = posting.get("jobLocation")
        locs = locs if isinstance(locs, list) else [locs] if locs else []
        cities = [((l or {}).get("address") or {}).get("addressLocality") for l in locs]
        if any(cities):
            job.location = ", ".join(c for c in cities if c)
    if not job.location:
        m = re.search(r'"jobLocations":(\[[^\]]*\])', payload)
        if m:
            try:
                job.location = ", ".join(x.get("city", "") for x in json.loads(m.group(1)) if x.get("city"))
            except json.JSONDecodeError:
                pass
    m = re.search(r'"properties":(\[\{"label".*?\}\])', payload)
    if m:
        try:
            for p in json.loads(m.group(1)):
                job.extra[p.get("label", "")] = p.get("value")
        except json.JSONDecodeError:
            pass

    soup = BeautifulSoup(page, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.body
    if main is not None:
        text = html_to_text(str(main), 20000)
        # Skip the generic "Career at WUR / About us" header block.
        m = re.search(r"\b(Your job|Jouw functie|Je functie)\b", text[:1500])
        if m:
            text = job.title + "\n" + text[m.start():]
        text = text[:8000]
        if len(text) > len(job.description):
            job.description = text
    return job
