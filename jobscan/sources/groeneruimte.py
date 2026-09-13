"""GroeneRuimte vacaturebank (AgriHolland) — vacancies in nature, landscape and green space.

Listing pages are plain HTML (10 per page, ?of=<offset>); enrich() fetches the detail page.
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text
from .nature_employers import find_deadline

NAME = "groeneruimte"
LIST = "https://www.groeneruimte.nl/vacaturebank/index.php"
MAX_PAGES = 15


def _nl_date(s: str) -> str | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for page in range(MAX_PAGES):
        r = get(LIST, params={"of": page * 10} if page else None)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("#results a[href]")
        new = 0
        for a in items:
            m = re.search(r"/vacaturebank/(\d+)/?$", a["href"])
            if not m or m.group(1) in jobs:
                continue
            title = a.select_one(".vacature_titel")
            niveau = a.select_one(".vacature_niveau")
            tekst = a.select_one(".tekst")
            org = a.select_one(".bedrnaam")
            org_name = org.get_text(" ", strip=True) if org else ""
            loc = ""
            if tekst:
                parts = [p.strip() for p in tekst.get_text("\n", strip=True).split("\n") if p.strip()]
                loc = parts[-1] if len(parts) > 1 else ""
            niveau_txt = niveau.get_text(" ", strip=True) if niveau else ""
            jobs[m.group(1)] = Job(
                source=NAME,
                source_id=m.group(1),
                url=urljoin(r.url, a["href"]),
                title=title.get_text(" ", strip=True) if title else a.get_text(" ", strip=True),
                organization=org_name,
                location=loc,
                posted=_nl_date(niveau_txt),
                extra={"education": niveau_txt.split("|")[0].strip()},
            )
            new += 1
        if not new or not soup.find("a", href=re.compile(rf"of={(page + 1) * 10}\b")):
            break
        time.sleep(0.5)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(0.5)
    try:
        html = get(job.url, retries=1).text
    except Exception:
        return job
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("#content.vactekst") or soup.select_one("#content") or soup.body
    for tag in root.select("script, style, form, button"):
        tag.decompose()
    text = html_to_text(str(root), 8000)
    job.description = text
    job.deadline = job.deadline or find_deadline(text)
    return job
