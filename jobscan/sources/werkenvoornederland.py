"""Werken voor Nederland — Dutch central government jobs (RIVM, NVWA, RVO, Rijkswaterstaat, ...).

The site (Bloomreach/Hippo CMS) loads results from an HTML fragment endpoint:
  /vacatures?_hn:type=resource&_hn:ref=<component>&_hn:rid=vacancy-results&term=...&vakgebied=...&pagina=N
We query a few relevant fields of work (vakgebied) plus keyword searches (`term`), dedupe,
and read deadline/posted dates from the listing. enrich() fetches the detail page text.
"""
from __future__ import annotations

import json
import re
import time

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text

NAME = "werkenvoornederland"
BASE = "https://www.werkenvoornederland.nl"
LIST = BASE + "/vacatures"
DEFAULT_REF = "r46_r1_r4"
PAGE_SIZE = 20
MAX_PAGES = 10

# Agrarisch, Natuur/milieu, Onderzoek/wetenschap, Medisch/verzorging
VAKGEBIEDEN = ["CVG.27", "CVG.28", "CVG.14", "CVG.12"]

# Search is fuzzy/substring-ish: short terms like "vis", "dier", "marien", "analist" or
# "onderzoeker" match most of the ~1300 ads, so they are deliberately left out.
SEARCH_TERMS = [
    "genetica", "genetics", "ecologie", "ecology", "biologie", "biology", "bioloog",
    "natuurbehoud", "natuur", "biodiversiteit", "biodiversity", "aquacultuur", "visserij",
    "dierenwelzijn", "diergezondheid", "laboratorium", "laborant", "bioinformatica",
    "bioinformatics", "wildlife", "zoologie", "promovendus", "PhD", "research",
    "veterinair", "NVWA", "RIVM", "Wageningen",
]

DUTCH_MONTHS = {m: i for i, m in enumerate(
    ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
     "september", "oktober", "november", "december"], start=1)}

_ref: str | None = None


def _nl_date(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", s.lower())
    if not m or m.group(2) not in DUTCH_MONTHS:
        return None
    return f"{int(m.group(3)):04d}-{DUTCH_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"


def _resource_url(ref: str) -> str:
    return f"{LIST}?_hn:type=resource&_hn:ref={ref}&_hn:rid=vacancy-results"


def _discover_ref() -> str:
    """Find the CMS component id that renders the results list (in case it changes)."""
    page = get(LIST).text
    for ref in re.findall(r"_hn:type=component-rendering&amp;_hn:ref=([\w]+)", page):
        frag = get(LIST, params={"_hn:type": "component-rendering", "_hn:ref": ref}).text
        m = re.search(r"_hn:ref=([\w]+)&amp;_hn:rid=vacancy-results", frag)
        if m:
            return m.group(1)
    raise RuntimeError("werkenvoornederland: results component not found")


def _query(params: dict) -> str:
    global _ref
    if _ref is None:
        _ref = DEFAULT_REF
    # requests would percent-encode the ':' in '_hn:ref'; build the base URL by hand.
    html = get(_resource_url(_ref), params=params).text
    if "vacancy-results-container" not in html:
        _ref = _discover_ref()
        html = get(_resource_url(_ref), params=params).text
    return html


def _parse(html: str, jobs: dict[str, Job]) -> tuple[int, int]:
    soup = BeautifulSoup(html, "html.parser")
    badge = soup.select_one(".vacancy-result-bar__totals-badge")
    total = int(re.sub(r"\D", "", badge.get_text())) if badge and re.search(r"\d", badge.get_text()) else 0
    items = soup.select("section.vacancy")
    for sec in items:
        a = sec.select_one(".vacancy__title a[href]")
        if not a:
            continue
        href = a["href"].split("?")[0]
        sid = href.rstrip("/").rsplit("/", 1)[-1]
        if sid in jobs:
            continue
        info: dict[str, str] = {}
        for li in sec.select("li.job-short-info__item"):
            icon = li.select_one("[title]")
            val = li.select_one(".job-short-info__value")
            if icon and val:
                info[icon["title"]] = re.sub(r"\s+", " ", val.get_text(" ", strip=True))
        emp = sec.select_one(".vacancy__employer")
        top = sec.select_one(".job-short-info__top")
        desc = sec.select_one(".vacancy__description")
        vtype = sec.select_one(".vacancy-type")
        end = sec.select_one(".vacancy-publication-end")
        jobs[sid] = Job(
            source=NAME,
            source_id=sid,
            url=BASE + href,
            title=a.get_text(" ", strip=True),
            organization=emp.get_text(" ", strip=True) if emp else "",
            location=info.get("Locatie", ""),
            description=desc.get_text(" ", strip=True) if desc else "",
            deadline=_nl_date(end.get_text(" ", strip=True) if end else info.get("Solliciteer voor")),
            posted=_nl_date(top.get_text(" ", strip=True) if top else None),
            extra={k: v for k, v in {
                "type": vtype.get_text(strip=True) if vtype else "",
                "hours": info.get("Uren per week", ""),
                "salary": info.get("Salaris", ""),
                "level": info.get("Niveau", ""),
                "contract": info.get("Arbeidsovereenkomst", ""),
            }.items() if v},
        )
    return total, len(items)


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    queries = [{"vakgebied": ",".join(VAKGEBIEDEN)}, {"type": "stage"}] + [{"term": t} for t in SEARCH_TERMS]
    for q in queries:
        for page in range(1, MAX_PAGES + 1):
            params = dict(q)
            if page > 1:
                params["pagina"] = page
            total, n = _parse(_query(params), jobs)
            time.sleep(0.3)
            if n < PAGE_SIZE or page * PAGE_SIZE >= total:
                break
    return list(jobs.values())


def enrich(job: Job) -> Job:
    html = get(job.url).text
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            ld = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "JobPosting":
            job.deadline = job.deadline or (ld.get("validThrough") or "")[:10] or None
            job.posted = job.posted or (ld.get("datePosted") or "")[:10] or None
            break
    # Main body: from the first section heading after the title up to "Relevante vacatures".
    m = re.search(r"<h2[^>]*>\s*Dit ga je doen", html)
    if m:
        start = m.start()
    else:
        h1 = html.find("<h1")
        start = h1 if h1 >= 0 else 0
    end = html.find("Relevante vacatures", start)
    if end < 0:
        end = start + 60000
    else:
        end = html.rfind("<h2", start, end)
    text = html_to_text(html[start:end], 8000)
    if len(text) > len(job.description):
        job.description = text
    time.sleep(0.5)
    return job
