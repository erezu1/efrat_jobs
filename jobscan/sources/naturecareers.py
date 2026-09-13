"""Nature Careers — jobs located in the Netherlands, via the Madgex RSS feed (LocationId=148).

Usually only a handful of NL jobs; enrich() reads JSON-LD (description, validThrough)
and the "Closing date" field from the detail page.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from .base import Job, get, html_to_text

NAME = "naturecareers"
RSS = "https://www.nature.com/naturecareers/jobsrss/"
NL_LOCATION_ID = "148"
MAX_PAGES = 10


def fetch() -> list[Job]:
    jobs: dict[str, Job] = {}
    for page in range(1, MAX_PAGES + 1):
        xml = get(RSS, params={"LocationId": NL_LOCATION_ID, "Page": page}).content
        root = ET.fromstring(xml)
        items = root.findall("./channel/item")
        new = 0
        for it in items:
            link = (it.findtext("link") or "").strip()
            m = re.search(r"/job/(\d+)/", link)
            if not m or m.group(1) in jobs:
                continue
            new += 1
            sid = m.group(1)
            raw_title = (it.findtext("title") or "").strip()
            org, _, title = raw_title.partition(": ")
            if not title:
                org, title = "", raw_title
            desc = (it.findtext("description") or "").strip()
            lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
            location = lines[-1] if lines and "(NL)" in lines[-1] else ""
            posted = None
            try:
                posted = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
            except (TypeError, ValueError):
                pass
            jobs[sid] = Job(
                source=NAME,
                source_id=sid,
                url=link.split("?")[0],
                title=title,
                organization=org,
                location=location,
                description=desc,
                posted=posted,
            )
        total = root.findtext("./channel/{http://a9.com/-/spec/opensearch/1.1/}totalResults")
        if new == 0 or not items or (total and total.isdigit() and len(jobs) >= int(total)):
            break
        time.sleep(0.5)
    return list(jobs.values())


def enrich(job: Job) -> Job:
    html = get(job.url).text
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            ld = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "JobPosting":
            text = html_to_text(ld.get("description"), 8000)
            if text:
                job.description = text
            if ld.get("validThrough"):
                job.deadline = str(ld["validThrough"])[:10]
            org = (ld.get("hiringOrganization") or {}).get("name")
            if org and not job.organization:
                job.organization = org
            break
    if not job.deadline:
        m = re.search(r"Closing date\s*</dt>\s*<dd[^>]*>\s*([^<]+)", html) or \
            re.search(r"Closing date(?:<[^>]+>|\s)*(\d{1,2} \w{3} \d{4})", html)
        if m:
            try:
                job.deadline = datetime.strptime(m.group(1).strip(), "%d %b %Y").date().isoformat()
            except ValueError:
                pass
    time.sleep(0.5)
    return job
