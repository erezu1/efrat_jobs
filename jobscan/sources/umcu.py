"""UMC Utrecht — werkenbijumcutrecht.nl (same career-site platform as UvA).

Mostly clinical/nursing/support jobs, but also research analysts, lab
technicians and PhD positions. Single Dutch listing; ?n=1000 returns all.
source_id = the numeric vacancy id at the end of the URL.
"""
from __future__ import annotations

from .base import Job
from ._werkenbij import enrich_job, fetch_jobs

NAME = "umcu"
LISTINGS = ["https://www.werkenbijumcutrecht.nl/vacatures"]


def fetch() -> list[Job]:
    return fetch_jobs(NAME, "UMC Utrecht", "Utrecht", LISTINGS)


def enrich(job: Job) -> Job:
    return enrich_job(job)
