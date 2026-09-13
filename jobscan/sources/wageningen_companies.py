"""Career pages of biology/genetics employers on or around Wageningen Campus.

There is no shared Wageningen Campus / StartLife job board (jobs.start-life.nl
is dead), so this module aggregates individual employers. Each entry in
COMPANIES names a fetcher type:

  wordpress         WP "careers" post type: the public careers page(s) decide
                    which vacancies are open; the RSS feed of the post type
                    supplies title/date/full text.
  recruitee         Recruitee public offers API (full text in listing).
  digitalrecruiters DigitalRecruiters careers-site API; the listing has only a
                    city, so each ad's detail JSON is fetched to keep NL ads.

Skipped (checked Sept 2026): CRV (AFAS OutSite, JS-only), Topigs Norsvin
(no vacancy page), Genetwister (careers page has no listings),
Hudson River Biotechnology (no careers page), Wetlands International and
De Vlinderstichting (JS-rendered / no vacancies; NGO boards covered elsewhere).
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from .base import Job, get, html_to_text, iso_date, session

NAME = "wageningen_companies"
DOMAIN_SPECIFIC = True

COMPANIES = [
    {"key": "keygene", "name": "KeyGene", "type": "wordpress", "location": "Wageningen",
     "feed": "https://www.keygene.com/?post_type=careers&feed=rss2",
     "listings": ["https://www.keygene.com/careers/"],
     "link_re": r"https://www\.keygene\.com/career/[a-z0-9-]+/",
     "content": "section.main-content"},
    {"key": "solynta", "name": "Solynta (hybrid potato breeding)", "type": "wordpress",
     "location": "Wageningen",
     "feed": "https://www.solynta.com/careers/feed/",
     "listings": ["https://www.solynta.com/careers/", "https://www.solynta.com/werkenbij/"],
     "link_re": r"https://www\.solynta\.com/careers/(?!feed/)[a-z0-9-]+/"},
    {"key": "nizo", "name": "NIZO (food & microbiology research)", "type": "wordpress",
     "location": "Ede",
     "feed": "https://www.nizo.com/?post_type=careers&feed=rss2",
     "listings": ["https://www.nizo.com/careers/"],
     "link_re": r"https://www\.nizo\.com/careers/(?!feed/)[a-z0-9-]+/",
     "content": "section.content"},
    {"key": "noldus", "name": "Noldus Information Technology", "type": "recruitee",
     "slug": "noldus"},
    {"key": "hendrix", "name": "Hendrix Genetics (animal & aquaculture breeding)",
     "type": "digitalrecruiters", "domain": "careers.hendrix-genetics.com", "country": "Netherlands"},
]

SKIP_TITLE = re.compile(r"(?i)\bopen (application|sollicitatie)\b")


def _job(c: dict, sid: str, **kw) -> Job:
    kw.setdefault("location", c.get("location", ""))
    return Job(source=NAME, source_id=f"{c['key']}:{sid}", organization=c["name"], **kw)


def _rss_date(s: str | None) -> str | None:
    try:
        return parsedate_to_datetime(s).date().isoformat() if s else None
    except (TypeError, ValueError):
        return None


def _fetch_wordpress(c: dict) -> list[Job]:
    open_links: list[str] = []
    for url in c["listings"]:
        for link in re.findall(c["link_re"], get(url).text):
            if link not in open_links:
                open_links.append(link)
    feed: dict[str, dict] = {}
    try:
        root = ET.fromstring(get(c["feed"]).content)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            feed[link] = {
                "title": html_to_text(item.findtext("title") or "", 300),
                "posted": _rss_date(item.findtext("pubDate")),
                "html": item.findtext("content:encoded", namespaces=ns) or item.findtext("description") or "",
            }
    except Exception:  # feed is a nicety; listing links still work
        pass
    jobs = []
    for link in open_links:
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        f = feed.get(link, {})
        title = f.get("title") or slug.replace("-", " ").capitalize()
        if SKIP_TITLE.search(title):
            continue
        desc = re.sub(r"(?s)\s*(The post|Het bericht) .{0,300}? (appeared first on|verscheen eerst op) .{0,80}$",
                      "", html_to_text(f.get("html"), 8000))
        jobs.append(_job(c, slug, url=link, title=title, description=desc,
                         posted=f.get("posted")))
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
                         description=desc[:8000],
                         deadline=iso_date(o.get("close_at")),
                         posted=iso_date(o.get("published_at")),
                         extra={"department": o.get("department"),
                                "employment_type": o.get("employment_type_code")}))
    return jobs


def _fetch_digitalrecruiters(c: dict) -> list[Job]:
    api = "https://api.digitalrecruiters.com/public/v1/careers-site/job-ads"
    base = {"domainName": c["domain"], "locale": "en_GB"}
    items, page = [], 1
    while page <= 5:
        resp = session().post(api, params={**base, "limit": 100, "page": page},
                              json={"filters": {}}, timeout=30)
        resp.raise_for_status()
        d = resp.json()
        items += d.get("items", [])
        if len(items) >= d.get("count", 0) or not d.get("items"):
            break
        page += 1
    jobs, seen = [], set()
    for it in items[:150]:
        if it.get("job_ad_id") in seen:
            continue
        seen.add(it.get("job_ad_id"))
        time.sleep(0.2)
        try:
            det = get(f"{api}/{it['job_ad_id']}", params=base).json()
        except Exception:
            continue
        addr = det.get("address") or {}
        if (addr.get("country") or "").lower() != c["country"].lower():
            continue
        desc = "\n\n".join(filter(None, [html_to_text(det.get("description"), 5000),
                                         html_to_text(det.get("profile"), 3000)]))
        jobs.append(_job(c, str(it["job_ad_id"]),
                         url=f"https://{c['domain']}/en/annonce/{it['url']}",
                         title=(det.get("title") or it.get("title") or "").strip(),
                         location=addr.get("city") or it.get("location") or "",
                         description=desc[:8000],
                         posted=iso_date((det.get("jsonld") or {}).get("datePosted")
                                         or det.get("republished_at")),
                         deadline=iso_date((det.get("jsonld") or {}).get("validThrough")),
                         extra={"contract": det.get("contract"), "job_family": it.get("job")}))
    return jobs


FETCHERS = {
    "wordpress": _fetch_wordpress,
    "recruitee": _fetch_recruitee,
    "digitalrecruiters": _fetch_digitalrecruiters,
}


def fetch() -> list[Job]:
    jobs: list[Job] = []
    for c in COMPANIES:
        try:
            jobs += FETCHERS[c["type"]](c)
        except Exception as e:  # one broken career page must not kill the rest
            print(f"[{NAME}] {c['key']} failed: {e}")
    return jobs


def enrich(job: Job) -> Job:
    """Only needed when a WordPress listing link was missing from the RSS feed."""
    if len(job.description) > 300 or not job.url:
        return job
    time.sleep(0.5)
    company = next((c for c in COMPANIES if job.source_id.startswith(c["key"] + ":")), {})
    soup = BeautifulSoup(get(job.url).text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"]):
        tag.decompose()
    body = soup.select_one(company["content"]) if company.get("content") else None
    if body is None:
        for tag in soup.find_all(class_=re.compile(r"(?i)menu|cookie|footer|header|newsletter")):
            tag.decompose()
        body = soup.find("article") or soup.find("main") or soup.body
    if body is not None:
        text = html_to_text(str(body), 8000)
        if len(text) > len(job.description):
            job.description = text
    return job
