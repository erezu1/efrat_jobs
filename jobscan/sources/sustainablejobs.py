"""Sustainablejobs.nl — sustainability / nature & environment job board (WordPress Job Manager).

The WP REST endpoint /wp-json/wp/v2/job-listings returns all published vacancies
with full content, so no enrich() is needed. The same code serves fondsen.org
(see fondsen.py).
"""
from __future__ import annotations

import datetime as dt
import time

from .base import Job, get, html_to_text, iso_date
from .nature_employers import find_deadline

NAME = "sustainablejobs"
BASE = "https://sustainablejobs.nl"
MAX_AGE_DAYS = 240   # the board keeps some stale posts published; drop very old ones


def fetch_wp_job_manager(base: str, source: str, max_age_days: int = MAX_AGE_DAYS) -> list[Job]:
    api = f"{base}/wp-json/wp/v2/job-listings"
    cutoff = (dt.date.today() - dt.timedelta(days=max_age_days)).isoformat()
    raw: list[dict] = []
    page, pages = 1, 1
    while page <= min(pages, 10):
        r = get(api, params={"per_page": 100, "page": page})
        pages = int(r.headers.get("X-WP-TotalPages", "1") or 1)
        raw.extend(r.json())
        page += 1
        time.sleep(0.3)

    # company names: meta often empty -> resolve job_company taxonomy terms
    term_ids = sorted({t for v in raw for t in (v.get("job_company") or [])})
    companies: dict[int, str] = {}
    for i in range(0, len(term_ids), 100):
        try:
            terms = get(f"{base}/wp-json/wp/v2/job_company",
                        params={"include": ",".join(map(str, term_ids[i:i + 100])), "per_page": 100}).json()
            companies.update({t["id"]: html_to_text(t.get("name")) for t in terms})
        except Exception:
            pass

    jobs: dict[str, Job] = {}
    for v in raw:
        meta = v.get("meta") or {}
        if meta.get("_filled"):
            continue
        posted = iso_date(v.get("date"))
        if posted and posted < cutoff:
            continue
        sid = str(v["id"])
        org = (meta.get("_company_name") or "").strip()
        if not org and v.get("job_company"):
            org = companies.get(v["job_company"][0], "")
        desc = html_to_text((v.get("content") or {}).get("rendered"), 8000)
        expires = iso_date(meta.get("_job_expires") or "")
        jobs[sid] = Job(
            source=source,
            source_id=sid,
            url=v.get("link", ""),
            title=html_to_text((v.get("title") or {}).get("rendered")),
            organization=org,
            location=meta.get("_job_location") or "",
            description=desc,
            deadline=find_deadline(desc),
            posted=posted,
            extra={"apply": meta.get("_application"), "salary": meta.get("_job_salary"),
                   "listing_expires": expires},
        )
    return list(jobs.values())


def fetch() -> list[Job]:
    return fetch_wp_job_manager(BASE, NAME)
