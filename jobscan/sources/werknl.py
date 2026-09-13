"""werk.nl (UWV) — the public-employment-service vacancy search (~250k NL vacancies, aggregated).

Keyless JSON API used by the werk.nl search app:
  GET  .../zoekenvacatures/api/configuration   -> sets the XSRF-TOKEN cookie
  POST .../zoekenvacatures/api/search          (header X-XSRF-TOKEN) -> 20 items per page
  GET  .../zoekenvacatures/api/vacature/{ref}  -> detail JSON (used by enrich)
General board: runs several NL/EN search terms and dedupes.
"""
from __future__ import annotations

import time

import requests

from .base import Job, get, html_to_text, iso_date, session

NAME = "werknl"
API = "https://www.werk.nl/werkzoekenden/mijn-werkmap/kia/publiek/zoekenvacatures/api"
SITE = "https://www.werk.nl/nl/vacatures/"

SEARCH_TERMS = [
    "genetica", "genetics", "genomics", "biologie", "bioloog", "biology", "moleculaire biologie",
    "microbiologie", "ecologie", "ecoloog", "ecology", "natuurbehoud", "natuurbeheer", "conservation",
    "biodiversiteit", "biodiversity", "aquacultuur", "aquaculture", "viskweek", "visserij", "fish",
    "fokkerij", "veredeling", "animal breeding", "laboratorium analist", "laborant", "lab technician",
    "research technician", "onderzoeksassistent", "bioinformatica", "bioinformatics", "zoologie",
    "dierentuin", "dierverzorger", "mariene biologie", "marine biology", "promovendus", "phd",
]
MAX_PAGES = 5  # 20 results per page


def _post_search(sess: requests.Session, token: str, term: str, page: int) -> dict:
    body = {"facets": [], "keywords": term, "location": "", "currentPage": page,
            "sort": {"by": 1, "direction": 1}, "keywordsChanged": False,
            "includeFirstExpansion": False, "includeSecondExpansion": False}
    for attempt in range(3):
        try:
            r = sess.post(f"{API}/search", json=body, timeout=30,
                          headers={"X-XSRF-TOKEN": token, "Accept": "application/json"})
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    return {}


def fetch() -> list[Job]:
    sess = session()
    get(f"{API}/configuration")
    token = sess.cookies.get("XSRF-TOKEN", domain=None) or ""
    if not token:
        raise RuntimeError("werk.nl XSRF-TOKEN cookie not set")
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        for page in range(1, MAX_PAGES + 1):
            d = _post_search(sess, token, term, page)
            items = d.get("items") or []
            for v in items:
                ref = str(v.get("referenceNumber") or "")
                if not ref or ref in jobs:
                    continue
                if v.get("workLocationForeignCountry"):
                    continue
                jobs[ref] = Job(
                    source=NAME, source_id=ref, url=SITE + ref,
                    title=(v.get("vacatureTitle") or v.get("profession") or "").strip(),
                    organization=v.get("organisation") or "",
                    location=(v.get("workLocationCity") or "").title(),
                    posted=iso_date(v.get("modified")),
                    extra={"profession": v.get("profession"), "contract": v.get("contractType"),
                           "education": v.get("studyLevel"), "stage": v.get("stageplaats"),
                           "search_term": term},
                )
            if len(items) < 20 or page * 20 >= (d.get("totalResults") or 0):
                break
            time.sleep(0.3)
        time.sleep(0.3)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(0.4)
    d = get(f"{API}/vacature/{job.source_id}", headers={"Accept": "application/json"}).json()
    prop = d.get("proposition") or {}
    func = prop.get("function") or {}
    cv = d.get("cvOffer") or {}
    parts = [
        html_to_text(func.get("description"), 6000),
        html_to_text(d.get("description"), 4000),
        html_to_text(prop.get("termsOfEmploymentDescription"), 1500),
        ("EISEN: " + html_to_text(cv.get("otherRequirements"), 1500)) if cv.get("otherRequirements") else "",
        ("OPLEIDING: " + (cv.get("educationLevel") or {}).get("name", "")) if cv.get("educationLevel") else "",
    ]
    job.description = "\n\n".join(p for p in parts if p)[:8000]
    emp = d.get("employer") or {}
    job.organization = emp.get("organizationName") or job.organization
    loc = prop.get("workLocation") or {}
    if loc.get("city"):
        job.location = loc["city"].title()
    job.posted = iso_date(d.get("createdDate")) or job.posted
    # expirationDate is UWV's automatic listing expiry, not an application deadline.
    job.extra["listing_expires"] = iso_date(d.get("expirationDate"))
    apply = [m.get("urlApplicationForm") for m in d.get("applicationMethods") or [] if m.get("urlApplicationForm")]
    if apply:
        job.extra["apply_url"] = apply[0]
    return job
