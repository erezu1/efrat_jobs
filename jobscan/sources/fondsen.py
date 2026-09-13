"""Fondsen.org — job board for Dutch charities / NGOs / nature organisations
(WordPress Job Manager REST API, same engine as sustainablejobs.nl)."""
from __future__ import annotations

from .base import Job
from .sustainablejobs import fetch_wp_job_manager

NAME = "fondsen"
BASE = "https://www.fondsen.org"


def fetch() -> list[Job]:
    return fetch_wp_job_manager(BASE, NAME)
