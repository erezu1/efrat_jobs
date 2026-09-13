"""Greenjobs.nl — Dutch sustainability / nature job board (Exenzo job-board public API).

The public listing endpoint returns full vacancy texts, so no enrich() is needed.
`till` is the ad's expiry on the board, not the application deadline; the real
deadline is sniffed from the text and `till` is kept in extra.
"""
from __future__ import annotations

import time

from .base import Job, get, html_to_text, iso_date
from .nature_employers import find_deadline

NAME = "greenjobs"
API = "https://greenjobs.api.exenzo.com/api/public/v1/job-boards/1/jobs"
SITE = "https://greenjobs.nl/vacature/"
MAX_PAGES = 10


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    page = 1
    last = 1
    while page <= min(last, MAX_PAGES):
        r = get(API, params={"page": page, "limit": 100}).json()
        last = r.get("lastPage") or 1
        for v in r.get("data", []):
            if v.get("status") != "active":
                continue
            if v.get("country_code") not in (None, "", "NL"):
                continue
            sid = str(v["id"])
            if sid in jobs:
                continue
            if v.get("text_type") == "platform":
                tp = v.get("text_platform") or {}
                body = "\n\n".join(html_to_text(tp.get(k), 4000) for k in ("job", "function", "company", "offer") if tp.get(k))
            else:
                body = html_to_text(v.get("text_own") or v.get("text_search"), 8000)
            desc = body or html_to_text(v.get("description"))
            url = (v.get("job_boards_url") or {}).get("greenjobs") or SITE + v.get("slug", "")
            jobs[sid] = Job(
                source=NAME,
                source_id=sid,
                url=url,
                title=(v.get("title") or "").strip(),
                organization=v.get("organisation_name") or "",
                location=v.get("city") or v.get("location_name") or "",
                description=desc[:8000],
                deadline=find_deadline(desc),
                posted=iso_date(v.get("from") or v.get("created_at")),
                extra={
                    "listing_expires": iso_date(v.get("till")),
                    "apply_url": v.get("apply_url"),
                    "hours": [v.get("hours_min"), v.get("hours_max")],
                    "salary_max": v.get("salary_max"),
                    "segments": v.get("segments_names"),
                },
            )
        page += 1
        time.sleep(0.3)
    return list(jobs.values())
