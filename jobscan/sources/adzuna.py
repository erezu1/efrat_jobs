"""Adzuna official job-search API (country nl). Needs a free key from developer.adzuna.com.

Reads ADZUNA_APP_ID / ADZUNA_APP_KEY from the environment; returns [] when unset.
Endpoint (per developer.adzuna.com/docs/search):
  GET https://api.adzuna.com/v1/api/jobs/nl/search/{page}?app_id=..&app_key=..
      &results_per_page=50&what=..&max_days_old=..&content-type=application/json
  -> {"count": N, "results": [{"id", "title", "description" (snippet), "redirect_url", "created",
      "company": {"display_name"}, "location": {"display_name", "area": [...]},
      "category": {"label"}, "contract_type", "contract_time", "salary_min", "salary_max"}]}
The API only returns a description snippet; enrich() tries the adzuna.nl details page.
"""
from __future__ import annotations

import os
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date

NAME = "adzuna"
API = "https://api.adzuna.com/v1/api/jobs/nl/search/{page}"

SEARCH_TERMS = [
    "genetica", "genetics", "genomics", "biologie", "biology", "moleculaire biologie", "ecologie",
    "ecology", "natuurbehoud", "conservation", "biodiversiteit", "biodiversity", "aquacultuur",
    "aquaculture", "viskweek", "fish", "fokkerij", "animal breeding", "veredeling",
    "laboratorium analist", "laborant", "lab technician", "research technician", "bioinformatics",
    "bioinformatica", "zoologie", "zoology", "marine biology", "mariene biologie", "phd",
]
MAX_PAGES = 3
RESULTS_PER_PAGE = 50
MAX_DAYS_OLD = 45


def fetch() -> list[Job]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        for page in range(1, MAX_PAGES + 1):
            d = get(API.format(page=page), params={
                "app_id": app_id, "app_key": app_key, "results_per_page": RESULTS_PER_PAGE,
                "what": term, "max_days_old": MAX_DAYS_OLD, "content-type": "application/json",
            }).json()
            results = d.get("results") or []
            for v in results:
                sid = str(v.get("id") or "")
                if not sid or sid in jobs:
                    continue
                jobs[sid] = Job(
                    source=NAME, source_id=sid, url=v.get("redirect_url") or "",
                    title=html_to_text(v.get("title"), 300),
                    organization=(v.get("company") or {}).get("display_name", ""),
                    location=(v.get("location") or {}).get("display_name", ""),
                    description=html_to_text(v.get("description"), 8000),
                    posted=iso_date(v.get("created")),
                    extra={"category": (v.get("category") or {}).get("label"),
                           "contract": [v.get("contract_type"), v.get("contract_time")],
                           "salary": [v.get("salary_min"), v.get("salary_max")],
                           "search_term": term},
                )
            if len(results) < RESULTS_PER_PAGE or page * RESULTS_PER_PAGE >= (d.get("count") or 0):
                break
            time.sleep(0.5)
        time.sleep(0.5)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    """Best effort: the adzuna.nl details page usually carries the full ad text."""
    time.sleep(0.5)
    try:
        soup = BeautifulSoup(get(f"https://www.adzuna.nl/details/{job.source_id}", retries=0).text,
                             "html.parser")
    except Exception:
        return job
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"]):
        tag.decompose()
    body = soup.select_one("section.adp-body, .adp-body") or soup.find("main") or soup.find("article")
    if body is not None:
        text = html_to_text(str(body), 8000)
        if len(text) > len(job.description):
            job.description = text
    return job
