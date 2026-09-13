"""werkzoeken.nl — large Dutch vacancy aggregator (~180k vacancies).

The search page is server-rendered: each result is a <section class="... feed-card"> whose
data-* attributes carry id, company, city, contract, hours and age. The SPA "feed-page"
action returns the first pnr*50 cards in one request. Detail pages (/vacature/...) sit
behind a Cloudflare challenge, but the SPA "vacancy-detail" fragment endpoint is open;
enrich() uses that.
"""
from __future__ import annotations

import html
import re
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text

NAME = "werkzoeken"
BASE = "https://www.werkzoeken.nl"

SEARCH_TERMS = [
    "genetica", "genetics", "genomics", "biologie", "bioloog", "biology", "moleculaire biologie",
    "microbiologie", "ecologie", "ecoloog", "ecology", "natuurbehoud", "natuurbeheer", "conservation",
    "biodiversiteit", "aquacultuur", "aquaculture", "viskweek", "visserij", "fokkerij", "veredeling",
    "laboratorium analist", "laborant", "lab technician", "research technician", "onderzoeksassistent",
    "bioinformatica", "bioinformatics", "zoologie", "dierentuin", "dierverzorger", "mariene biologie",
    "promovendus",
]
PAGES = 3  # feed-page with pnr=3 returns up to 150 cards in one request

_CARD = re.compile(r'<section class="component-card[^"]*feed-card"([^>]*)>(.*?)</section>', re.S)
_ATTR = re.compile(r'data-([\w-]+)="([^"]*)"')
_TITLE = re.compile(r'<a class="feed-card__link" href="([^"]+)">(.*?)</a>', re.S)


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        params = {"reqtype": "spa", "reqrouter": "vacancy", "action": "feed-page",
                  "what": term, "where": "", "r": "", "filtered": "0", "pnr": PAGES}
        page = get(f"{BASE}/vacatures/", params=params).text
        for attrs_s, inner in _CARD.findall(page):
            a = {k: html.unescape(v) for k, v in _ATTR.findall(attrs_s)}
            vid = a.get("vacancyid")
            if not vid or vid in jobs:
                continue
            m = _TITLE.search(inner)
            path = a.get("url") or (m.group(1) if m else "")
            title = html_to_text(m.group(2), 300) if m else ""
            jobs[vid] = Job(
                source=NAME, source_id=vid, url=BASE + path if path.startswith("/") else path,
                title=title, organization=a.get("business", ""),
                location=a.get("location-label", ""),
                extra={"contract": a.get("contract-type"), "hours": a.get("hours"),
                       "age": a.get("age"), "business_type": a.get("business-type"),
                       "search_term": term},
            )
        time.sleep(1.0)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    time.sleep(0.7)
    r = get(f"{BASE}/vacatures/", params={"reqtype": "spa", "reqrouter": "vacancy",
                                           "action": "vacancy-detail", "vacancyid": job.source_id})
    soup = BeautifulSoup(r.text, "html.parser")
    sec = soup.select_one("section.ajax-page-vacancy-detail")
    if sec is None:
        return job
    for tag in sec(["script", "style", "button", "svg", "form"]):
        tag.decompose()
    for tag in sec.select(".vacancy-report-container, .vacancy-hero-mobile, .vacancy-scrolled-desktop"):
        tag.decompose()
    body = sec.select_one(".ajax-page-body") or sec
    text = html_to_text(str(body), 8000)
    # Drop the generic "how applying works" footer.
    text = re.split(r"\n\s*Zo werkt solliciteren", text)[0].strip()
    if len(text) > len(job.description):
        job.description = text
    return job
