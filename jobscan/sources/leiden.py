"""Leiden University — careers.universiteitleiden.nl (SAP SuccessFactors Career Site Builder).

universiteitleiden.nl/en/vacancies and /vacatures are CSB pages whose job list
is rendered client-side from a public JSON endpoint:
    POST /services/recruiting/v1/jobs  {"locale": ..., "pageNumber": n}
It returns 10 jobs per page with id, title, faculty (filter1), location and
unifiedStandardEnd (= application deadline; "M/D/YY" for en_US, "DD-MM-YYYY"
for nl_NL). The English and Dutch locales list partly different ads, so both are
queried and merged by id. Includes JobMotion (Leiden's staffing agency) ads.

Detail page: /job/<urlTitle>/<id>-<locale>/ with the ad in [itemprop=description].
source_id = the requisition id (e.g. "16748").
"""
from __future__ import annotations

import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, session
from ._nldate import find_deadline, parse_date

NAME = "leiden"
BASE = "https://careers.universiteitleiden.nl"
API = BASE + "/services/recruiting/v1/jobs"
LOCALES = ["en_US", "nl_NL"]


def _post(payload: dict, retries: int = 2) -> dict:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session().post(API, json=payload, timeout=30,
                               headers={"Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def _end_date(s: str | None, locale: str) -> str | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s.strip())
    if m:  # en_US: M/D/YY
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        try:
            return date(y, int(m[1]), int(m[2])).isoformat()
        except ValueError:
            return None
    return parse_date(s)  # nl_NL: DD-MM-YYYY


def _all_results(locale: str) -> list[dict]:
    """All job records for a locale.

    The endpoint's paging is not stable (ties in the sort order shuffle between
    requests, so pages can overlap and miss jobs). Sorting by date is mostly
    stable; we additionally repeat the sweep (union by id) until we have
    totalJobs unique records, up to a few passes.
    """
    seen: dict[str, dict] = {}
    total = None
    for sweep in range(4):
        page = 0
        while page < 100:
            data = _post({
                "locale": locale, "pageNumber": page,
                "sortBy": "date" if sweep % 2 == 0 else "", "keywords": "",
                "location": "", "facetFilters": {}, "brand": "", "skills": [],
                "categoryId": 0, "alertId": "", "rcmCandidateId": "",
            })
            total = data.get("totalJobs", total)
            results = data.get("jobSearchResult") or []
            if not results:
                break
            for item in results:
                r = item.get("response") or {}
                if r.get("id"):
                    seen.setdefault(str(r["id"]), r)
            page += 1
        if total is not None and len(seen) >= total:
            break
        time.sleep(1)
    return list(seen.values())


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for locale in LOCALES:
        for r in _all_results(locale):
            sid = str(r["id"])
            if sid in jobs:
                continue
            url_title = r.get("urlTitle") or r.get("unifiedUrlTitle") or "job"
            faculty = ", ".join(r.get("filter1") or [])
            other_org = r.get("cust_OtherOrganisation") or ""
            org = "Leiden University"
            if other_org:
                org += f" — {other_org}"
            elif faculty:
                org += f" — {faculty}"
            loc = ", ".join(r.get("locaties") or []) or r.get("cust_OtherLocation") or "Leiden"
            jobs[sid] = Job(
                source=NAME,
                source_id=sid,
                url=f"{BASE}/job/{url_title}/{sid}-{locale}/",
                title=(r.get("unifiedStandardTitle") or "").strip(),
                organization=org,
                location=loc,
                description=faculty,
                deadline=_end_date(r.get("unifiedStandardEnd"), locale),
                posted=_end_date(r.get("unifiedStandardStart"), locale),
                extra={"locale": locale},
            )
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(1)
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    node = soup.select_one("span[itemprop=description], div[itemprop=description]")
    if node is None:
        for tag in soup.select("script, style, nav, header, footer"):
            tag.decompose()
        node = soup.select_one(".jobDisplay, .job, main") or soup.body
    text = html_to_text(str(node), 8000) if node else ""
    if len(text) > len(job.description or ""):
        job.description = text
    if not job.deadline:
        job.deadline = find_deadline(text)
    return job
