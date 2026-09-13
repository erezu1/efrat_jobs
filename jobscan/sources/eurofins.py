"""Eurofins Netherlands — large network of food / environment / pharma / forensic-DNA labs.

Many lab analyst / technician roles, but also lots of generic jobs (drivers, sales, HR),
so this source is NOT marked DOMAIN_SPECIFIC: the keyword prefilter should apply.
Uses the public SmartRecruiters postings API; enrich() pulls the full ad text.
"""
from __future__ import annotations

from .base import Job
from . import industry

NAME = "eurofins"

_COMPANY = {"key": "eurofins", "name": "Eurofins", "type": "smartrecruiters", "company": "Eurofins"}


def fetch() -> list[Job]:
    jobs = industry._fetch_smartrecruiters(_COMPANY)
    for j in jobs:
        j.source = NAME
        j.source_id = j.source_id.split(":", 1)[1]
    return jobs


def enrich(job: Job) -> Job:
    return industry.enrich(job)
