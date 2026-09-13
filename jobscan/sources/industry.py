"""Industry employers in animal/plant breeding, aquaculture feed and genomics with NL sites.

Each entry in COMPANIES names a fetcher type (one per ATS / site technology):

  nutreco         careers.nutreco.com JSON API (Nutreco, Trouw Nutrition, Skretting)
  workday         Workday "cxs" JSON API, filtered on the Netherlands country facet
  smartrecruiters SmartRecruiters public postings API (country=nl)
  recruitee       Recruitee public offers API (full text in listing)
  emply           Emply career site (POST /api/integration/vacancy/get-page, full text)
  dummen          Dümmen Orange vacancies JSON (app/vacancies/overview.web)
  afas            AFAS OutSite portal: category pages embed the vacancy list as JSON
  wp_rest         WordPress REST API post type with full content
  html_links      plain listing page; vacancy links matched by regex, text via enrich()

All ads from these employers are in-domain (breeding / genetics / feed / biotech),
hence DOMAIN_SPECIFIC = True.

Not included here:
  - Hendrix Genetics and KeyGene: already covered by the wageningen_companies source.
  - Eurofins NL: large generic lab employer, separate `eurofins` source (not domain-specific).
  - Rijk Zwaan (rijkzwaan.com/.nl) and Syngenta.nl site: Cloudflare 403 to scripts
    (Syngenta NL jobs are fetched via SmartRecruiters instead).
  - Aviagen, Genus/PIC, Alltech Coppens: no NL vacancies found in their ATS.
  - Vion: meat processing, out of scope.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date, session

NAME = "industry"
DOMAIN_SPECIFIC = True

COMPANIES = [
    {"key": "nutreco", "name": "Nutreco / Trouw Nutrition / Skretting", "type": "nutreco"},
    {"key": "enza", "name": "Enza Zaden (vegetable breeding)", "type": "workday",
     "tenant": "enzazaden", "host": "enzazaden.wd103.myworkdayjobs.com", "site": "Enza-Careers"},
    {"key": "cobb", "name": "Cobb Europe (poultry breeding)", "type": "workday",
     "tenant": "tysonfoods", "host": "tysonfoods.wd5.myworkdayjobs.com", "site": "CVT"},
    {"key": "syngenta", "name": "Syngenta (seeds / vegetable breeding)", "type": "smartrecruiters",
     "company": "SyngentaGroup"},
    {"key": "genomescan", "name": "GenomeScan (genomics lab)", "type": "recruitee",
     "slug": "genomescan"},
    {"key": "koppert", "name": "Koppert (biological control)", "type": "emply",
     "base": "https://werkenbijkoppert.nl", "lang": "nl"},
    {"key": "dummen", "name": "Dümmen Orange (plant breeding)", "type": "dummen"},
    {"key": "crv", "name": "CRV (cattle breeding)", "type": "afas",
     "base": "https://vacature.crv4all.nl",
     "portals": ["cooperatie", "genetica", "in-het-veld", "information-solutions", "internationaal",
                 "logistiek-en-productie", "salesenmarketing", "staffuncties", "stages"]},
    {"key": "topigs", "name": "Topigs Norsvin (pig genetics)", "type": "wp_rest",
     "api": "https://www.werkenbijtopigsnorsvin.nl/wp-json/wp/v2/posts", "location": "Den Bosch / Beuningen",
     "max_age_days": 365},
    {"key": "baseclear", "name": "BaseClear (genomics lab)", "type": "wp_rest",
     "api": "https://www.baseclear.com/wp-json/wp/v2/career-job", "location": "Leiden"},
    {"key": "bejo", "name": "Bejo Zaden (vegetable seed breeding)", "type": "html_links",
     "listings": ["https://www.werkenbijbejo.nl/vacatures", "https://www.werkenbijbejo.nl/vacatures?page=1"],
     "link_re": r"^/vacatures/[a-z0-9-]+-(\d+)$", "base": "https://www.werkenbijbejo.nl",
     "location": "Warmenhuizen"},
]

NL_WORDS = re.compile(r"(?i)netherlands|nederland|\bNL\b")
SKIP_TITLE = re.compile(r"(?i)\bopen (internship )?(application|sollicitatie)\b")
NON_NL_LOC = re.compile(r"(?i)vlaanderen|antwerpen|waasland|belgi[eëu]|\bbelgium\b")


# ---------------------------------------------------------------- helpers

def _job(c: dict, sid: str, **kw) -> Job:
    kw.setdefault("location", c.get("location", ""))
    return Job(source=NAME, source_id=f"{c['key']}:{sid}", organization=c["name"], **kw)


def _post(url: str, *, json_body=None, params=None, headers=None, retries: int = 2) -> requests.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session().post(url, json=json_body, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
MONTHS.update({m: i + 1 for i, m in enumerate(
    ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
     "september", "oktober", "november", "december"])})
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["okt"] = 10
MONTHS["mrt"] = 3

_DEADLINE_CUE = re.compile(
    r"(?i)(deadline|closing date|application date|apply (?:before|by|until)|applications? (?:close|until)|"
    r"sluitingsdatum|reageren (?:kan )?(?:voor|tot|uiterlijk)|solliciteren (?:kan )?(?:tot|voor|uiterlijk)|"
    r"uiterlijk|reageer (?:voor|uiterlijk)|open until|vacature sluit)")
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(rf"(?i)\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\.?,?\s+(\d{{4}})"),
     lambda m: (int(m[3]), MONTHS[m[2].lower()], int(m[1]))),
    (re.compile(rf"(?i)\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})"),
     lambda m: (int(m[3]), MONTHS[m[1].lower()], int(m[2]))),
]


def find_deadline(text: str) -> str | None:
    """Find a date shortly after a deadline cue ('closing date', 'reageren voor', ...)."""
    for cue in _DEADLINE_CUE.finditer(text or ""):
        window = text[cue.end(): cue.end() + 60]
        best = None
        for rx, conv in _DATE_PATTERNS:
            m = rx.search(window)
            if m and (best is None or m.start() < best[0]):
                try:
                    best = (m.start(), date(*conv(m)).isoformat())
                except (ValueError, KeyError):
                    pass
        if best:
            return best[1]
    return None


def _page_text(url: str, selector: str | None = None) -> str:
    soup = BeautifulSoup(get(url).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "iframe"]):
        tag.decompose()
    body = soup.select_one(selector) if selector else None
    if body is None:
        body = soup.find("main") or soup.find("article") or soup.body or soup
    return html_to_text(str(body), 8000)


# ---------------------------------------------------------------- fetchers

def _fetch_nutreco(c: dict) -> list[Job]:
    api = "https://careers.nutreco.com/api/vacancy/"
    headers = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    jobs = []
    page, pages = 1, 1
    while page <= min(pages, 40):
        d = get(api, params={"sort": "created", "sortDir": "DESC", "pageNumber": page}, headers=headers).json()
        pages = (d.get("meta") or {}).get("totalPageCount") or 1
        for v in d.get("vacancies", []):
            if (v.get("country") or "") not in ("Netherlands", "Nederland"):
                continue
            brands = [o.get("value") for o in v.get("option_values", [])
                      if (o.get("option") or {}).get("slug") == "business-lines"]
            areas = [o.get("title") for o in (v.get("subtitle") or {}).get("option_values", [])]
            jobs.append(Job(
                source=NAME, source_id=f"{c['key']}:{v['id']}",
                url=f"https://careers.nutreco.com/vacancy/{v['id']}/{v.get('slug', '')}",
                title=(v.get("title") or "").strip(),
                organization=brands[0] if brands else "Nutreco",
                location=(v.get("city") or "").replace("_", "."),
                posted=iso_date(v.get("created")),
                extra={"area": areas, "enrich": "page", "selector": "main"},
            ))
        page += 1
        time.sleep(0.3)
    return jobs


def _wd_flat(values):
    for v in values or []:
        if "values" in v:
            yield from _wd_flat(v["values"])
        else:
            yield v


def _fetch_workday(c: dict) -> list[Job]:
    api = f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
    first = _post(api, json_body={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}).json()
    # Find the Netherlands country facet (nested under locationMainGroup on most tenants).
    applied: dict[str, list[str]] = {}
    for f in first.get("facets", []):
        groups = f.get("values", [])
        nested = [g for g in groups if "values" in g]
        for g in nested or [f]:
            param = g.get("facetParameter") or f.get("facetParameter")
            if "country" not in (param or "").lower():
                continue
            for v in _wd_flat(g.get("values", [])):
                if re.search(r"(?i)netherlands|nederland", v.get("descriptor", "")):
                    applied.setdefault(param, []).append(v["id"])
    if not applied:
        return []
    jobs, offset = [], 0
    while offset < 400:
        d = _post(api, json_body={"appliedFacets": applied, "limit": 20, "offset": offset, "searchText": ""}).json()
        posts = d.get("jobPostings", [])
        for p in posts:
            path = p.get("externalPath", "")
            if not path:
                continue
            req = (p.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
            jobs.append(_job(c, req, url=f"https://{c['host']}/{c['site']}{path}",
                             title=(p.get("title") or "").strip(),
                             location=p.get("locationsText", ""),
                             extra={"enrich": "workday", "api": f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}{path}"}))
        if len(posts) < 20:
            break
        offset += 20
        time.sleep(0.3)
    return jobs


def _fetch_smartrecruiters(c: dict) -> list[Job]:
    api = f"https://api.smartrecruiters.com/v1/companies/{c['company']}/postings"
    jobs, offset = [], 0
    while offset < 1000:
        d = get(api, params={"country": "nl", "limit": 100, "offset": offset}).json()
        for p in d.get("content", []):
            loc = p.get("location") or {}
            if (loc.get("country") or "").lower() != "nl":
                continue
            jobs.append(_job(c, str(p["id"]),
                             url=f"https://jobs.smartrecruiters.com/{c['company']}/{p['id']}",
                             title=(p.get("name") or "").strip(),
                             location=loc.get("city") or loc.get("fullLocation") or "",
                             posted=iso_date(p.get("releasedDate")),
                             extra={"enrich": "smartrecruiters", "api": f"{api}/{p['id']}",
                                    "department": (p.get("department") or {}).get("label"),
                                    "function": (p.get("function") or {}).get("label")}))
        offset += 100
        if offset >= d.get("totalFound", 0):
            break
    return jobs


def _fetch_recruitee(c: dict) -> list[Job]:
    data = get(f"https://{c['slug']}.recruitee.com/api/offers/").json()
    jobs = []
    for o in data.get("offers", []):
        if o.get("status") not in (None, "published") or SKIP_TITLE.search(o.get("title", "")):
            continue
        if o.get("country_code") not in (None, "", "NL"):
            continue
        desc = "\n\n".join(filter(None, [html_to_text(o.get("description"), 5000),
                                         html_to_text(o.get("requirements"), 3000)]))
        jobs.append(_job(c, str(o["id"]), url=o.get("careers_url", ""), title=o.get("title", "").strip(),
                         location=o.get("city") or o.get("location") or "",
                         description=desc[:8000], deadline=iso_date(o.get("close_at")),
                         posted=iso_date(o.get("published_at"))))
    return jobs


def _fetch_emply(c: dict) -> list[Job]:
    base, lang = c["base"], c.get("lang", "nl")
    page = get(f"{base}/{lang}/vacatures").text
    m = re.search(r"sectionId:\s*'([0-9a-f-]{36})'", page)
    if not m:
        raise RuntimeError("Emply sectionId not found")
    lang_key = (re.search(r"var languageKey = '([\w-]+)'", page) or [None, "nl-NL"])[1]
    jobs, offset, total = [], 0, 1
    while offset < min(total, 300):
        d = _post(f"{base}/api/integration/vacancy/get-page", json_body={
            "count": 50, "filters": [], "langCode": lang_key, "offset": offset, "searchText": "",
            "sectionId": m.group(1), "sortByProjectDataId": "job_title", "sortAscending": True,
            "light": False, "isJobAgent": False, "siteId": None}).json()
        vs = d.get("vacancies", [])
        total = d.get("count", 0)
        for v in vs:
            if v.get("talentPool") or SKIP_TITLE.search(v.get("title", "")):
                continue
            tr = (v.get("translations") or [{}])[0]
            loc = v.get("location") or ""
            if loc and re.search(r"(?i)\b(belgi|deutschland|germany|spain|france|united)", loc) and not NL_WORDS.search(loc):
                continue
            jobs.append(_job(c, v.get("shortId") or v["id"],
                             url=v.get("externalCseAdLink") or f"{base}/{lang}/ad/{v.get('titleAsUrl')}/{v.get('shortId')}",
                             title=(v.get("title") or "").strip(),
                             location=loc,
                             description=html_to_text(tr.get("content"), 8000),
                             deadline=iso_date(v.get("deadline")),
                             posted=iso_date(v.get("published") or v.get("created")),
                             extra={"department": v.get("department")}))
        if not vs:
            break
        offset += len(vs)
    return jobs


def _fetch_dummen(c: dict) -> list[Job]:
    site = "https://emea.dummenorange.com"
    d = get(f"{site}/app/vacancies/overview.web", headers={"X-Requested-With": "XMLHttpRequest",
                                                        "Accept": "application/json"}).json()
    jobs = []
    for v in d.get("allVacancies", []):
        if not NL_WORDS.search(v.get("address") or ""):
            continue
        jobs.append(_job(c, str(v.get("id") or v.get("url")), url=site + v.get("url", ""),
                         title=(v.get("title") or "").strip(),
                         location=v.get("address") or "",
                         description=v.get("description") or "",
                         posted=iso_date(v.get("publishedDate")),
                         extra={"disciplines": v.get("disciplines"), "enrich": "page", "selector": "main"}))
    return jobs


def _fetch_afas(c: dict) -> list[Job]:
    base = c["base"]
    cat_pages: list[str] = []
    for p in c["portals"]:
        try:
            html = get(f"{base}/portal-over-het-bedrijf/{p}").text
        except requests.RequestException:
            continue
        for link in re.findall(r'href="(/[\w-]+-vacatures/[\w-]+)"', html):
            if link not in cat_pages:
                cat_pages.append(link)
        time.sleep(0.2)
    jobs: dict[str, Job] = {}
    row = re.compile(r'"link":"(\\/[^"]+)","columns":\{"U001":\{"value":"((?:[^"\\]|\\.)*)"\},'
                     r'"U002":\{"value":"((?:[^"\\]|\\.)*)"\}')
    for cp in cat_pages:
        html = get(base + cp).text
        for link, title, loc in row.findall(html):
            link = json.loads(f'"{link}"')
            slug = link.rstrip("/").rsplit("/", 1)[-1]
            if slug in jobs:
                continue
            title = json.loads(f'"{title}"')
            if SKIP_TITLE.search(title):
                continue
            jobs[slug] = _job(c, slug, url=base + link, title=title.strip(), location=json.loads(f'"{loc}"'),
                              extra={"category": cp.rsplit("/", 1)[-1], "enrich": "page", "selector": "main"})
        time.sleep(0.2)
    return list(jobs.values())


def _fetch_wp_rest(c: dict) -> list[Job]:
    items = get(c["api"], params={"per_page": 100,
                                  "_fields": "id,link,title,date,modified,content"}).json()
    cutoff = None
    if c.get("max_age_days"):
        cutoff = (datetime.now() - timedelta(days=c["max_age_days"])).date().isoformat()
    jobs = []
    for it in items:
        posted = iso_date(it.get("date"))
        if cutoff and (iso_date(it.get("modified")) or posted or "") < cutoff:
            continue
        title = html_to_text((it.get("title") or {}).get("rendered"), 300)
        if SKIP_TITLE.search(title):
            continue
        desc = html_to_text((it.get("content") or {}).get("rendered"), 8000)
        jobs.append(_job(c, str(it["id"]), url=it.get("link", ""), title=title, description=desc,
                         posted=posted, deadline=find_deadline(desc)))
    return jobs


def _fetch_html_links(c: dict) -> list[Job]:
    jobs: dict[str, Job] = {}
    rx = re.compile(c["link_re"])
    for url in c["listings"]:
        soup = BeautifulSoup(get(url).text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].split("?")[0].split("#")[0]
            m = rx.search(href)
            if not m:
                continue
            sid = m.group(1) if m.groups() else href.rstrip("/").rsplit("/", 1)[-1]
            if sid in jobs:
                continue
            head = a.find(["h2", "h3", "h4", "strong"])
            title = head.get_text(" ", strip=True) if head else ""
            if not title:
                slug = href.rstrip("/").rsplit("/", 1)[-1]
                title = re.sub(r"-\d+$", "", slug).replace("-", " ").capitalize()
            full = href if href.startswith("http") else c["base"] + href
            jobs[sid] = _job(c, sid, url=full, title=title,
                             extra={"card": a.get_text(" ", strip=True)[:300], "enrich": "page"})
        time.sleep(0.3)
    return list(jobs.values())


FETCHERS = {
    "nutreco": _fetch_nutreco,
    "workday": _fetch_workday,
    "smartrecruiters": _fetch_smartrecruiters,
    "recruitee": _fetch_recruitee,
    "emply": _fetch_emply,
    "dummen": _fetch_dummen,
    "afas": _fetch_afas,
    "wp_rest": _fetch_wp_rest,
    "html_links": _fetch_html_links,
}


def fetch() -> list[Job]:
    jobs: list[Job] = []
    for c in COMPANIES:
        try:
            jobs += [j for j in FETCHERS[c["type"]](c)
                     if not SKIP_TITLE.search(j.title) and not NON_NL_LOC.search(j.location)]
        except Exception as e:  # one broken career page must not kill the rest
            print(f"[{NAME}] {c['key']} failed: {e}")
    return jobs


# ---------------------------------------------------------------- enrich

def _enrich_workday(job: Job) -> None:
    info = get(job.extra["api"], headers={"Accept": "application/json"}).json().get("jobPostingInfo", {})
    job.description = html_to_text(info.get("jobDescription"), 8000)
    job.posted = iso_date(info.get("startDate")) or job.posted
    job.deadline = iso_date(info.get("endDate")) or find_deadline(job.description)
    if info.get("location"):
        job.location = info["location"]


def _enrich_smartrecruiters(job: Job) -> None:
    d = get(job.extra["api"]).json()
    sections = (d.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        s = sections.get(key) or {}
        if s.get("text"):
            parts.append((s.get("title") or key).upper() + ":\n" + html_to_text(s["text"], 4000))
    job.description = "\n\n".join(parts)[:8000]
    job.deadline = find_deadline(job.description)


def enrich(job: Job) -> Job:
    kind = job.extra.get("enrich")
    if not kind:
        return job
    time.sleep(0.5)
    if kind == "workday":
        _enrich_workday(job)
    elif kind == "smartrecruiters":
        _enrich_smartrecruiters(job)
    elif kind == "page":
        text = _page_text(job.url, job.extra.get("selector"))
        if len(text) > len(job.description):
            job.description = text
        job.deadline = job.deadline or find_deadline(text)
    for k in ("enrich", "api", "selector"):
        job.extra.pop(k, None)
    return job
