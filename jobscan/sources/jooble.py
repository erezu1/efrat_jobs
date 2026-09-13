"""Jooble REST API (aggregator). Needs a free key from jooble.org/api/about.

Reads JOOBLE_API_KEY from the environment; returns [] when unset.
  POST https://jooble.org/api/{key}  JSON {"keywords": "...", "location": "Nederland", "page": "1"}
  -> {"totalCount": N, "jobs": [{"id", "title", "location", "snippet", "salary", "source",
      "type", "link", "company", "updated"}]}
Note: the public docs page only shows this shape after sign-up; it was not verifiable
without a key, and jooble.org served a Cloudflare challenge to scripts during testing
(Sept 2026), so this may fail even with a valid key. Failures are logged, not raised.
"""
from __future__ import annotations

import os
import time

import requests

from .base import Job, html_to_text, iso_date, session

NAME = "jooble"

SEARCH_TERMS = [
    "genetica", "genetics", "genomics", "biologie", "biology", "ecologie", "ecology",
    "natuurbehoud", "conservation", "biodiversiteit", "aquacultuur", "aquaculture", "fokkerij",
    "veredeling", "laboratorium analist", "laborant", "lab technician", "research technician",
    "bioinformatics", "zoologie", "marine biology", "mariene biologie",
]
MAX_PAGES = 2


def fetch() -> list[Job]:
    key = os.environ.get("JOOBLE_API_KEY")
    if not key:
        return []
    url = f"https://jooble.org/api/{key}"
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        for page in range(1, MAX_PAGES + 1):
            try:
                r = session().post(url, json={"keywords": term, "location": "Nederland", "page": str(page)},
                                   headers={"Content-Type": "application/json"}, timeout=30)
                r.raise_for_status()
                d = r.json()
            except (requests.RequestException, ValueError) as e:
                print(f"[{NAME}] '{term}' page {page} failed: {e}")
                break
            items = d.get("jobs") or []
            for v in items:
                sid = str(v.get("id") or v.get("link") or "")
                if not sid or sid in jobs:
                    continue
                jobs[sid] = Job(
                    source=NAME, source_id=sid, url=v.get("link") or "",
                    title=html_to_text(v.get("title"), 300),
                    organization=v.get("company") or "",
                    location=v.get("location") or "",
                    description=html_to_text(v.get("snippet"), 8000),
                    posted=iso_date(v.get("updated")),
                    extra={"salary": v.get("salary"), "type": v.get("type"),
                           "origin": v.get("source"), "search_term": term},
                )
            if not items:
                break
            time.sleep(0.5)
    return list(jobs.values())
