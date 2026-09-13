"""EURAXESS — EU researcher job portal, restricted to offers located in the Netherlands.

The search page ignores the `keywords` parameter when requested without a browser
session, but the country facet (`job_country:798` = Netherlands) works and the NL
result set is small (a few hundred), so we simply page through all of it.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from .base import Job, get, html_to_text

NAME = "euraxess"
BASE = "https://euraxess.ec.europa.eu"
SEARCH = BASE + "/jobs/search"
NL_FACET = "job_country:798"
MAX_PAGES = 80  # 10 results per page
PAGE_SLEEP = 2.0  # CloudFront returns 429 after ~25 rapid requests


def _get(url: str, params=None) -> str:
    """base.get with extra patience for HTTP 429 rate limiting."""
    for attempt in range(4):
        try:
            return get(url, params=params).text
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 429 or attempt == 3:
                raise
            time.sleep(30 * (attempt + 1))
    raise RuntimeError("unreachable")


def _parse_date(s: str | None) -> str | None:
    """'11 Oct 2026 - 21:59 (UTC)' or '13 September 2026' -> '2026-10-11'."""
    if not s:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s)
    if not m:
        return None
    d, mon, y = m.groups()
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(f"{d} {mon[:3] if fmt == '%d %b %Y' else mon} {y}", fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _meta_value(item, cls: str) -> str:
    box = item.select_one(f"div.{cls}")
    if not box:
        return ""
    val = box.select_one("div.ecl-text-standard")
    return re.sub(r"\s+", " ", val.get_text(" ", strip=True)) if val else ""


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for page in range(MAX_PAGES):
        try:
            html = _get(SEARCH, params={
                "f[0]": NL_FACET, "sort[name]": "created", "sort[direction]": "DESC", "page": page,
            })
        except requests.RequestException:
            if jobs:  # keep what we have (sorted newest first) rather than failing the source
                break
            raise
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select('ul[aria-label="Search results items"] > li')
        if not items:
            break
        new = 0
        for li in items:
            a = li.select_one("h3.ecl-content-block__title a[href]")
            if not a:
                continue
            m = re.search(r"/jobs/(\d+)", a["href"])
            if not m:
                continue
            sid = m.group(1)
            if sid in jobs:
                continue
            country = li.select_one(".ecl-label--highlight")
            if country and country.get_text(strip=True) not in ("Netherlands", ""):
                continue
            new += 1
            primary = [x.get_text(" ", strip=True) for x in li.select(".ecl-content-block__primary-meta-item")]
            org = primary[0] if primary else ""
            posted = next((_parse_date(p) for p in primary if p.lower().startswith("posted")), None)
            loc = _meta_value(li, "id-Work-Locations")
            loc = re.sub(r"^Number of offers:\s*\d+,\s*", "", loc)
            field = _meta_value(li, "id-Research-Field")
            profile = _meta_value(li, "id-Researcher-Profile")
            snippet = li.select_one(".ecl-content-block__description")
            jobs[sid] = Job(
                source=NAME,
                source_id=sid,
                url=f"{BASE}/jobs/{sid}",
                title=a.get_text(" ", strip=True),
                organization=org,
                location=loc,
                description=snippet.get_text(" ", strip=True) if snippet else "",
                deadline=_parse_date(_meta_value(li, "id-Application-Deadline")),
                posted=posted,
                extra={"research_field": field, "researcher_profile": profile},
            )
        if new == 0 and page > 0:
            break
        if not soup.select_one(f'a[href*="page={page + 1}"]'):
            break
        time.sleep(PAGE_SLEEP)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(1.5)
    try:
        html = _get(job.url)
    except requests.RequestException:
        return job  # keep listing snippet
    soup = BeautifulSoup(html, "html.parser")
    parts = []
    for sec_id, label in [("offer-description", ""), ("requirements", "REQUIREMENTS"),
                          ("additional-information", "ADDITIONAL INFORMATION")]:
        h = soup.find(id=sec_id)
        if not h:
            continue
        body = h.find_next_sibling()
        if body is None:
            continue
        text = html_to_text(str(body), 5000)
        if text:
            parts.append(f"{label}:\n{text}" if label else text)
    if parts:
        job.description = "\n\n".join(parts)[:8000]
    info = soup.find(id="job-information")
    if info:
        dl = info.find_next("dl")
        if dl:
            for dt in dl.find_all("dt"):
                key = dt.get_text(" ", strip=True)
                dd = dt.find_next_sibling("dd")
                val = dd.get_text(" ", strip=True) if dd else ""
                if key == "Application Deadline" and not job.deadline:
                    job.deadline = _parse_date(val)
                elif key == "Organisation/Company" and not job.organization:
                    job.organization = val
                elif key in ("Type of Contract", "Job Status", "Hours Per Week"):
                    job.extra[key.lower().replace(" ", "_")] = val
    return job
