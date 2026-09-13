"""Career pages of Dutch conservation / natural-history / zoo / nature-NGO employers.

Most employers have small hand-built vacancy pages, so the generic strategy is:
fetch each listing page, pick vacancy links with a CSS selector + URL regex, and
let enrich() pull the detail page (JSON-LD JobPosting if present, else main text)
and sniff a deadline out of the text. A few employers have better structured
sources (NIOZ -> Recruitee API, EAZA -> vacancy table, Staatsbosbeheer -> paged
FacetWP listing) and get dedicated handlers.

Also exports small helpers (find_deadline, page_text, jsonld_jobposting) used by
the green job-board modules.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date

NAME = "nature_employers"
DOMAIN_SPECIFIC = True

# ---------------------------------------------------------------------------
# Deadline parsing (Dutch + English)
# ---------------------------------------------------------------------------
MONTHS = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2,
    "maart": 3, "march": 3, "mrt": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "augustus": 8, "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    # 28 september 2026 / 28 sept. 2026 / 28th of September 2026 / 28 september
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th|e)?(?:\s+of)?\s+({_MON})\.?,?(?:\s+(\d{{4}}))?\b", re.I),
    # September 28, 2026
    re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?(?:\s+(\d{{4}}))?\b", re.I),
    # 28-09-2026 / 28/09/2026 / 28.09.2026 / 28-9-26
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"),
    # 2026-09-28
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]
_KEYWORDS = re.compile(
    r"(?i)(sluitingsdatum|sluit\s+op|deadline|reageren\s+(?:kan|is\s+mogelijk)|reageer\s+(?:vóór|voor|uiterlijk|tot)|"
    r"solliciteren\s+(?:kan|is\s+mogelijk)|sollicit\w*\s+(?:vóór|voor|uiterlijk|tot)|uiterlijk|"
    r"t/m|tot\s+en\s+met|vóór|reactietermijn|open\s+tot|apply\s+(?:by|before|until|no\s+later)|"
    r"applications?\s+(?:close|deadline|must|should|until|before)|closing\s+date|no\s+later\s+than|"
    r"application\s+period|vacature\s+sluit|staat\s+open\s+tot|kun\s+je\s+reageren\s+tot)"
)

# a date followed by these is a start date / project milestone, not an application deadline
_NOT_DEADLINE = re.compile(r"(?i)\b(starten|start|beginnen|begin|in dienst|aan de slag|vast te stellen|gerealiseerd|opgeleverd|afgerond)\b")


def _mk_date(y: int | None, m: int, d: int, ref: dt.date) -> dt.date | None:
    try:
        if y is None:
            cand = dt.date(ref.year, m, d)
            if (ref - cand).days > 180:
                cand = dt.date(ref.year + 1, m, d)
            return cand
        if y < 100:
            y += 2000
        return dt.date(y, m, d)
    except ValueError:
        return None


def _dates_in(s: str, ref: dt.date) -> list[tuple[int, dt.date]]:
    out = []
    for i, pat in enumerate(_DATE_PATTERNS):
        for m in pat.finditer(s):
            g = m.groups()
            if i == 0:
                d = _mk_date(int(g[2]) if g[2] else None, MONTHS[g[1].lower()], int(g[0]), ref)
            elif i == 1:
                d = _mk_date(int(g[2]) if g[2] else None, MONTHS[g[0].lower()], int(g[1]), ref)
            elif i == 2:
                d = _mk_date(int(g[2]), int(g[1]), int(g[0]), ref)
            else:
                d = _mk_date(int(g[0]), int(g[1]), int(g[2]), ref)
            if d:
                out.append((m.start(), d))
    return sorted(out)


def find_deadline(text: str, ref: dt.date | None = None) -> str | None:
    """Find an application deadline in free text: a date shortly after a deadline keyword."""
    if not text:
        return None
    ref = ref or dt.date.today()
    for km in _KEYWORDS.finditer(text):
        window = text[km.end(): km.end() + 90]
        ds = _dates_in(window, ref)
        for pos, d in ds:
            after = window[pos: pos + 60]
            if _NOT_DEADLINE.search(after):
                continue
            # plausible deadline: not ancient, not absurdly far away
            if -400 <= (d - ref).days <= 400:
                return d.isoformat()
    return None


# ---------------------------------------------------------------------------
# Detail-page helpers
# ---------------------------------------------------------------------------
def jsonld_jobposting(html: str) -> dict | None:
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                t = item.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return item
                if "@graph" in item:
                    stack.extend(item["@graph"] if isinstance(item["@graph"], list) else [item["@graph"]])
            elif isinstance(item, list):
                stack.extend(item)
    return None


def page_text(html: str, limit: int = 8000) -> str:
    """Main readable text of a page (drops nav/header/footer/scripts)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "svg", "iframe", "button"]):
        tag.decompose()
    junk = re.compile(r"(?i)(^|[-_ ])(menu|navbar|navigation|nav|cookie|breadcrumb|skip|share|social|site-header|site-footer|topbar)([-_ ]|$)")
    for tag in soup.find_all(True):
        if tag.attrs is None:
            continue
        ident = " ".join(tag.get("class") or []) + " " + (tag.get("id") or "")
        if tag.name not in ("html", "body", "main", "article") and junk.search(ident):
            tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body or soup
    return html_to_text(str(root), limit)


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True)
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return og["content"].strip()
    return soup.title.get_text(strip=True) if soup.title else ""


# ---------------------------------------------------------------------------
# Employer config
# ---------------------------------------------------------------------------
# Each entry: org, location, listing URLs, CSS selector for <a>, URL regex that
# a vacancy link must match, optional URL regex to exclude.
EMPLOYERS = [
    dict(org="Naturalis Biodiversity Center", location="Leiden",
         urls=["https://www.naturalis.nl/over-ons/werken-bij-naturalis",
               "https://www.naturalis.nl/en/about-us/job-opportunities"],
         link=r"naturalis\.nl/(?:over-ons/werken-bij-naturalis|en/about-us/job-opportunities)/[^/?#]+$"),
    dict(org="ARTIS", location="Amsterdam",
         urls=["https://www.artis.nl/nl/over-artis/werken-bij/vacatures-stages"],
         link=r"^https://artis\.homerun\.co/[^/?#]+"),
    dict(org="Diergaarde Blijdorp (Rotterdam Zoo)", location="Rotterdam",
         urls=["https://werkenbij.diergaardeblijdorp.nl/vacatures",
               "https://werkenbij.diergaardeblijdorp.nl/stages"],
         link=r"^https://werkenbij\.diergaardeblijdorp\.nl/[a-z0-9-]+$",
         exclude=r"/(vacatures|stages|contact|kom-binnen-kijken|vrijwilligers|vrijwilligerswerk)$"),
    dict(org="Burgers' Zoo", location="Arnhem",
         urls=["https://www.burgerszoo.nl/werkenbij/dier-plantenverzorging",
               "https://www.burgerszoo.nl/werkenbij/technisch",
               "https://www.burgerszoo.nl/werkenbij/horecavacatures",
               "https://www.burgerszoo.nl/werkenbij/stages",
               "https://www.burgerszoo.com/vacancies"],
         link=r"burgerszoo\.(?:nl/werkenbij|com/vacancies)/[a-z0-9-]+/[a-z0-9-]+$|burgerszoo\.com/vacancies/[a-z0-9-]+$",
         exclude=r"/vrijwilligers|open-stage-vacature"),
    dict(org="Ouwehands Dierenpark", location="Rhenen",
         urls=["https://www.ouwehand.nl/nl/over-ouwehand/werken-bij-ouwehand"],
         link=r"/werken-bij-ouwehand/[a-z0-9-]+$", exclude=r"vrijwilliger"),
    dict(org="Apenheul", location="Apeldoorn",
         urls=["https://www.apenheul.nl/over-apenheul/werken-bij-apenheul"],
         link=r"/werken-bij-apenheul/[a-z0-9-]+$", exclude=r"vrijwillig"),
    dict(org="GaiaZOO", location="Kerkrade",
         urls=["https://www.gaiazoo.nl/werken-bij-gaiazoo/"],
         link=r"gaiazoo\.nl/werken-bij-gaiazoo/[a-z0-9-]+/?$"),
    dict(org="WWF-NL (Wereld Natuur Fonds)", location="Zeist",
         urls=["https://werkenbij.wwf.nl/vacatures/nederland"],
         link=r"werkenbij\.wwf\.nl/vacatures/(?:stages/)?[a-z0-9-]+$",
         exclude=r"/vacatures/(nederland|stages|vrijwilligers)$|/vrijwilligers/"),
    dict(org="Vogelbescherming Nederland", location="Zeist",
         urls=["https://www.vogelbescherming.nl/over-ons/werken-bij-vogelbescherming/vacatures-vogelbescherming"],
         link=r"/vacatures-vogelbescherming/[a-z0-9-]+$"),
    dict(org="Sovon Vogelonderzoek Nederland", location="Nijmegen",
         urls=["https://www.sovon.nl/over-sovon/werken-bij-sovon", "https://www.sovon.nl/vacatures"],
         link=r"sovon\.nl/vacature-[a-z0-9-]+$|sovon\.nl/vacatures/[a-z0-9-]+$"),
    dict(org="RAVON", location="Nijmegen",
         urls=["https://www.ravon.nl/werken-bij/"],
         link=r"ravon\.nl/vacatures/[a-z0-9-]+/?$"),
    dict(org="De Vlinderstichting", location="Wageningen",
         urls=["https://vlinderstichting.nl/over-ons/werken-bij/vacatures/",
               "https://vlinderstichting.nl/over-ons/werken-bij/stage-en-afstuderen/"],
         link=r"vlinderstichting\.nl/over-ons/werken-bij/(?:vacatures|stage-en-afstuderen)/[a-z0-9-]+/?$"),
    dict(org="Zodion (Zoogdiervereniging)", location="Nijmegen",
         urls=["https://www.zodion.nl/over-ons/al-onze-vacatures"],
         link=r"zodion\.nl/over-ons/(?:al-onze-vacatures|vacatures)/[a-z0-9-]+$"),
    dict(org="IUCN NL", location="Amsterdam",
         urls=["https://www.iucn.nl/organisatie/vacatures/"],
         selector="main .wp-block-paragraph a[href], main .wp-block-heading a[href], main li a[href]",
         link=r"^https://www\.iucn\.nl/", exclude=r"/organisatie/vacatures/?$|/contact"),
    dict(org="Wetlands International", location="Ede",
         urls=["https://www.wetlands.org/vacancies/"],
         selector="main a[href]",
         link=r"wetlands\.org/(?:vacanc|job|career)[a-z0-9-]*/[a-z0-9-]+/?$|recruitee|homerun|workable|teamtailor",
         exclude=r"/vacancies/?$|/vacancies/https?"),
    dict(org="ARK Rewilding Nederland", location="Nijmegen",
         urls=["https://arkrewilding.nl/over-ons/werken-bij-ark/vacatures"],
         link=r"arkrewilding\.nl/over-ons/werken-bij-ark/vacatures/[a-z0-9-]+$|arkrewilding\.nl/vacature"),
    dict(org="Zeehondencentrum Pieterburen", location="Pieterburen",
         urls=["https://www.zeehondencentrum.nl/vacatures/"],
         selector="main a[href], article a[href], .entry-content a[href]",
         link=r"zeehondencentrum\.nl/(?:vacature|stage)[a-z0-9-]*/[a-z0-9-]+/?$",
         exclude=r"/vacatures/?$"),
]

GENERIC_ANCHOR = re.compile(r"(?i)^(solliciteer( nu| direct)?!?|lees meer|bekijk\b.*|meer info(rmatie)?|read more|apply( now)?|ontdek meer|details|vacature|more)$")


def _slug_title(url: str) -> str:
    slug = [p for p in urlparse(url).path.split("/") if p]
    slug = slug[-1] if slug else url
    if slug in ("nl", "en") and len([p for p in urlparse(url).path.split("/") if p]) > 1:
        slug = [p for p in urlparse(url).path.split("/") if p][-2]
    slug = re.sub(r"-\d{5,}$", "", slug)
    return re.sub(r"[-_]+", " ", slug).strip().capitalize()


def _clean_anchor(a) -> str:
    head = a.find(["h1", "h2", "h3", "h4", "strong"])
    txt = head.get_text(" ", strip=True) if head else a.get_text(" ", strip=True)
    txt = re.sub(r"\s*\|\s*IUCN NL$", "", txt)
    txt = re.sub(r"\s+", " ", txt)
    if not txt or GENERIC_ANCHOR.match(txt) or len(txt) > 160:
        return ""
    return txt


def _generic(emp: dict) -> list[Job]:
    found: dict[str, Job] = {}
    link_re = re.compile(emp["link"], re.I)
    excl_re = re.compile(emp["exclude"], re.I) if emp.get("exclude") else None
    for listing in emp["urls"]:
        try:
            r = get(listing, retries=1)
        except Exception as e:  # one broken site must not kill the source
            print(f"[{NAME}] {emp['org']}: {listing} failed: {e}", file=sys.stderr)
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["nav", "header", "footer"]):
            tag.decompose()
        for a in soup.select(emp.get("selector", "a[href]")):
            href = urljoin(r.url, a["href"].strip()).split("#")[0]
            href_cmp = href.split("?")[0].rstrip("/") if "homerun" not in href else href.split("?")[0]
            if not link_re.search(href_cmp if not href_cmp.endswith("/") else href_cmp):
                if not link_re.search(href):
                    continue
            if excl_re and excl_re.search(href.split("?")[0]):
                continue
            if href.split("?")[0].rstrip("/") == listing.rstrip("/"):
                continue
            if href.lower().endswith((".jpg", ".png")):
                continue
            # stable id: homerun uses /<slug>/nl variants -> normalise
            key_url = href.split("?")[0].rstrip("/")
            key_url = re.sub(r"(homerun\.co/[^/]+)/(nl|en)$", r"\1", key_url)
            title = _clean_anchor(a)
            if key_url in found:
                if title and found[key_url].extra.get("title_from_slug"):
                    found[key_url].title = title
                    found[key_url].extra.pop("title_from_slug", None)
                continue
            job = Job(source=NAME, source_id=key_url.split("://", 1)[1], url=href,
                      title=title or _slug_title(key_url), organization=emp["org"],
                      location=emp.get("location", ""), extra={"employer": emp["org"]})
            if not title:
                job.extra["title_from_slug"] = True
            found[key_url] = job
    return list(found.values())


def _nioz() -> list[Job]:
    data = get("https://nioz.recruitee.com/api/offers/").json().get("offers", [])
    jobs = []
    for o in data:
        if o.get("status") != "published" or re.search(r"(?i)open (sollicitatie|application)", o.get("title", "")):
            continue
        desc = "\n\n".join(filter(None, [
            html_to_text(o.get("description"), 5500),
            "REQUIREMENTS:\n" + html_to_text(o.get("requirements"), 2400) if o.get("requirements") else "",
        ]))
        jobs.append(Job(
            source=NAME, source_id=f"nioz:{o['id']}", url=o.get("careers_url", ""),
            title=o.get("title", "").strip(), organization="NIOZ Royal Netherlands Institute for Sea Research",
            location=o.get("city") or o.get("location", ""), description=desc[:8000],
            deadline=iso_date(o.get("close_at")) or find_deadline(desc),
            posted=iso_date(o.get("published_at")),
            extra={"employer": "NIOZ", "department": o.get("department"), "tags": o.get("tags"),
                   "employment_type": o.get("employment_type_code"), "full_text": True},
        ))
    return jobs


def _eaza() -> list[Job]:
    """EAZA vacancy table (members + Executive Office). Keep only Netherlands-based rows."""
    r = get("https://www.eaza.net/vacancies/")
    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a = tds[0].find("a", href=True)
        title = re.sub(r"^NEW!\s*", "", tds[0].get_text(" ", strip=True)).strip()
        where = tds[1].get_text(" ", strip=True)
        if not a or title.upper() == "VACANCY":
            continue
        if not re.search(r"(?i)netherlands|nederland|amsterdam|EAZA Executive Office|\bNL\b", where):
            continue
        url = urljoin(r.url, a["href"])
        deadline_txt = tds[2].get_text(" ", strip=True)
        jobs.append(Job(
            source=NAME, source_id="eaza:" + re.sub(r"[^a-z0-9]+", "-", (title + "-" + where).lower()).strip("-"),
            url=url, title=title, organization=where.split(",")[0].strip() + " (via EAZA)",
            location=where, deadline=find_deadline("deadline " + deadline_txt),
            description=f"EAZA vacancy listing. Vacancy: {title}. Location: {where}. Deadline: {deadline_txt}.",
            extra={"employer": "EAZA", "pdf": url.lower().endswith(".pdf")},
        ))
    return jobs


def _staatsbosbeheer() -> list[Job]:
    base = "https://werkenbijstaatsbosbeheer.nl/vacatures/"
    found: dict[str, Job] = {}
    pages = 1
    page = 1
    while page <= min(pages, 15):
        r = get(base, params={"_paged": page} if page > 1 else None)
        m = re.search(r'"total_pages":(\d+)', r.text)
        if m:
            pages = int(m.group(1))
        soup = BeautifulSoup(r.text, "html.parser")
        new = 0
        for a in soup.select("a[href]"):
            href = urljoin(r.url, a["href"])
            mm = re.search(r"werkenbijstaatsbosbeheer\.nl/vacatures/([a-z0-9-]+-(\d{6,}))/?$", href)
            if not mm or mm.group(2) in found:
                continue
            title = _clean_anchor(a) or _slug_title(href)
            found[mm.group(2)] = Job(source=NAME, source_id=f"sbb:{mm.group(2)}", url=href, title=title,
                                     organization="Staatsbosbeheer", location="",
                                     extra={"employer": "Staatsbosbeheer"})
            new += 1
        if not new:
            break
        page += 1
        time.sleep(0.5)
    return list(found.values())


SPECIAL = [("NIOZ", _nioz), ("EAZA", _eaza), ("Staatsbosbeheer", _staatsbosbeheer)]


def fetch() -> list[Job]:
    jobs: list[Job] = []
    for name, fn in SPECIAL:
        try:
            jobs.extend(fn())
        except Exception as e:
            print(f"[{NAME}] {name} failed: {e}", file=sys.stderr)
    for emp in EMPLOYERS:
        try:
            jobs.extend(_generic(emp))
        except Exception as e:
            print(f"[{NAME}] {emp['org']} failed: {e}", file=sys.stderr)
        time.sleep(0.3)
    seen, out = set(), []
    for j in jobs:
        if j.source_id not in seen:
            seen.add(j.source_id)
            out.append(j)
    return out


def enrich(job: Job) -> Job:
    if job.extra.get("full_text") or job.url.lower().endswith(".pdf"):
        return job
    time.sleep(0.5)
    try:
        r = get(job.url, retries=1)
    except Exception as e:
        print(f"[{NAME}] enrich failed for {job.url}: {e}", file=sys.stderr)
        return job
    html = r.text
    jp = jsonld_jobposting(html)
    text = ""
    if jp and jp.get("description"):
        text = html_to_text(html_to_text(jp["description"], 20000), 8000)
        if not job.posted:
            job.posted = iso_date(jp.get("datePosted"))
        loc = jp.get("jobLocation")
        if isinstance(loc, list) and loc:
            loc = loc[0]
        if isinstance(loc, dict) and not job.location:
            job.location = (loc.get("address") or {}).get("addressLocality", "") if isinstance(loc.get("address"), dict) else ""
    if len(text) < 300:
        text = page_text(html)
    if job.extra.get("title_from_slug"):
        t = (jp or {}).get("title") or page_title(html)
        if t:
            job.title = t.strip()
            job.extra.pop("title_from_slug", None)
    closed = re.search(r"(?i)vacature gesloten|deze vacature is gesloten|vacancy (is )?closed|no longer accepting applications", html_to_text(html, 100000))
    if closed:
        job.extra["closed"] = True
        text = "[NOTE: the vacancy page says this position is CLOSED]\n" + text
    job.description = text[:8000]
    if not job.deadline:
        job.deadline = find_deadline(text)
        vt = iso_date(str((jp or {}).get("validThrough") or ""))
        if not job.deadline and vt and vt >= "2020":
            job.extra["valid_through"] = vt  # listing expiry, not necessarily the application deadline
    return job
