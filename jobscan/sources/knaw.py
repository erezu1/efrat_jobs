"""KNAW vacancies (vacatures.knaw.nl) — all institutes of the Royal Netherlands
Academy of Arts and Sciences: NIOO (ecology), Westerdijk Fungal Biodiversity
Institute, Hubrecht Institute, Netherlands Institute for Neuroscience,
Humanities Cluster, IISG, ...

SAP SuccessFactors career site. The search page is JS-rendered, but its
backing JSON endpoint (/services/recruiting/v1/jobs) works with the CSRF token
embedded in the search page. The listing includes institute, city and the
posting end date (deadline); enrich() fetches the ad body.

Note: NIOO's student internships are NOT posted here — see the `nioo` source.
"""
from __future__ import annotations

import html
import re
import time
from datetime import datetime

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, session

NAME = "knaw"
BASE = "https://vacatures.knaw.nl"
API = BASE + "/services/recruiting/v1/jobs"
LOCALES = ["nl_NL", "en_US"]   # some ads only exist in one locale
MAX_PAGES = 10


def _dmy(s: str | None) -> str | None:
    for fmt in ("%d-%m-%Y", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _first(v):
    return (v[0] if v else "") if isinstance(v, list) else (v or "")


def fetch() -> list[Job]:
    page = get(BASE + "/search/").text
    m = re.search(r'CSRFToken\s*=\s*"([^"]+)"', page)
    headers = {"X-CSRF-Token": m.group(1)} if m else {}
    jobs: dict[str, Job] = {}
    for locale in LOCALES:
        for page_no in range(MAX_PAGES):
            body = {"locale": locale, "pageNumber": page_no, "sortBy": "date", "keywords": "",
                    "location": "", "facetFilters": {}, "brand": "", "skills": [],
                    "categoryId": 0, "alertId": "", "rcmCandidateId": ""}
            r = session().post(API, json=body, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()
            results = data.get("jobSearchResult") or []
            for res in results:
                v = res.get("response") or {}
                sid = str(v.get("id") or "")
                if not sid or sid in jobs:
                    continue
                loc = (v.get("supportedLocales") or [locale])[0]
                institute = _first(v.get("custOrg1"))
                jobs[sid] = Job(
                    source=NAME,
                    source_id=sid,
                    url=f"{BASE}/job/{html.unescape(v.get('urlTitle') or v.get('unifiedUrlTitle') or '')}/{sid}-{loc}",
                    title=(v.get("unifiedStandardTitle") or "").strip(),
                    organization="KNAW" + (f" — {institute}" if institute else ""),
                    location=_first(v.get("custLocatie")),
                    deadline=_dmy(v.get("unifiedStandardEnd")),
                    posted=_dmy(v.get("unifiedStandardStart")),
                    extra={"institute": institute, "locale": loc},
                )
            if not results or (page_no + 1) * 10 >= int(data.get("totalJobs") or 0):
                break
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(0.5)
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    parts = [e.get_text("\n", strip=True) for e in soup.select("[itemprop=description]")]
    desc = html_to_text("\n\n".join(p for p in parts if p), 8000)
    # Key/value tokens (institute, location, end date, hours, salary, contract).
    facts = {}
    for tok in soup.select(".joblayouttoken"):
        t = tok.get_text(" ", strip=True)
        k, sep, val = t.partition(":")
        if sep and len(k) < 60 and val.strip():
            facts.setdefault(k.strip(), val.strip())
    job.extra.update(facts)
    if not job.deadline:
        end = next((v for k, v in facts.items() if re.search(r"(?i)end date|einddatum|sluitingsdatum", k)), None)
        job.deadline = _dmy(end)
    if facts:
        desc = "\n".join(f"{k}: {v}" for k, v in facts.items()) + "\n\n" + desc
    if len(desc) > len(job.description):
        job.description = desc[:8000]
    return job
