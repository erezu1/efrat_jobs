"""University of Amsterdam — werkenbij.uva.nl.

The Dutch (/vacatures) and English (/en/vacancies) listings hold *different*
ads (Dutch-language vs English-language vacancies; ids don't overlap), so both
are fetched. Parsing is shared with UMC Utrecht in _werkenbij.py.
source_id = the numeric vacancy id at the end of the URL.
"""
from __future__ import annotations

from .base import Job
from ._werkenbij import enrich_job, fetch_jobs

NAME = "uva"
LISTINGS = [
    "https://werkenbij.uva.nl/en/vacancies",
    "https://werkenbij.uva.nl/vacatures",
]


def fetch() -> list[Job]:
    return fetch_jobs(NAME, "University of Amsterdam", "Amsterdam", LISTINGS)


def enrich(job: Job) -> Job:
    return enrich_job(job)
