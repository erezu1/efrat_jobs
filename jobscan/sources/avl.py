"""Netherlands Cancer Institute – Antoni van Leeuwenhoek (werkenbijavl.nl): all vacancies, incl. research."""
from __future__ import annotations

import time

from bs4 import BeautifulSoup

from ._nldate import parse_date
from .base import Job, get, html_to_text

NAME = "avl"
BASE = "https://www.werkenbijavl.nl"
ORG = "Netherlands Cancer Institute – Antoni van Leeuwenhoek"
MAX_PAGES = 30


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for page in range(1, MAX_PAGES + 1):
        soup = BeautifulSoup(get(f"{BASE}/vacatures/", params={"page": page}).text, "html.parser")
        cards = soup.select("a.searchResult")
        new = 0
        for a in cards:
            href = a.get("href", "")
            slug = href.strip("/").split("/")[-1]
            if not slug or slug in jobs:
                continue
            title = a.select_one(".searchResult-title")
            date = a.select_one(".searchResult-date")
            jobs[slug] = Job(
                source=NAME, source_id=slug, url=BASE + href,
                title=title.get_text(" ", strip=True) if title else slug.replace("-", " "),
                organization=ORG, location="Amsterdam",
                deadline=parse_date(date.get_text(" ", strip=True).replace("Sluitingsdatum:", "")) if date else None,
            )
            new += 1
        if not cards or not new:
            break
        time.sleep(0.5)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    content = soup.select_one(".umb-tpl-Vacancy-content") or soup.body
    job.description = html_to_text(str(content), 8000)
    if not job.deadline:
        dt = next((d for d in soup.find_all("dt") if "Sluitingsdatum" in d.get_text()), None)
        if dt and dt.find_next("dd"):
            job.deadline = parse_date(dt.find_next("dd").get_text(" ", strip=True))
    time.sleep(0.4)
    return job
