"""AcademicTransfer — the main Dutch academic job board (uses its public JSON API)."""
from __future__ import annotations

import json
import re

from .base import Job, get, html_to_text, iso_date

NAME = "academictransfer"
API = "https://api.academictransfer.com/vacancies/"
SITE = "https://www.academictransfer.com/en/jobs/"

SEARCH_TERMS = [
    "genetics", "genomics", "population genetics", "conservation", "biodiversity",
    "ecology", "evolution", "aquaculture", "fish", "animal breeding", "animal science",
    "wildlife", "endangered species", "zoology", "marine biology", "molecular biology",
    "bioinformatics", "technician biology", "genetica", "ecologie",
]


def _token() -> str:
    # The website embeds a public read-only token in its page state.
    # Nuxt payload is a flat array; the state object maps the key to an array index.
    page = get(SITE, params={"q": "genetics"}).text
    data = re.search(r'__NUXT_DATA__"[^>]*>(\[.*?\])</script>', page, re.S)
    if data:
        arr = json.loads(data.group(1))
        for item in arr:
            if isinstance(item, dict) and "$satDataApiPublicAccessToken" in item:
                val = arr[item["$satDataApiPublicAccessToken"]]
                if isinstance(val, str) and len(val) > 20:
                    return val
    raise RuntimeError("AcademicTransfer public token not found")


def fetch() -> list[Job]:
    headers = {"Authorization": f"Bearer {_token()}"}
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        offset = 0
        while offset < 300:
            r = get(API, headers=headers, params={
                "is_active": "true", "search": term, "limit": 100, "offset": offset,
            }).json()
            for v in r.get("results", []):
                if v.get("country_code") not in (None, "", "NL"):
                    continue
                sid = str(v.get("external_id") or v["id"])
                if sid in jobs:
                    continue
                tr = next((t for t in v.get("translations", []) if t.get("language_code") == "en"),
                          (v.get("translations") or [{}])[0])
                desc = "\n\n".join(filter(None, [
                    html_to_text(tr.get("description"), 5000),
                    "REQUIREMENTS:\n" + html_to_text(tr.get("requirements"), 3000) if tr.get("requirements") else "",
                    "CONTRACT: " + html_to_text(tr.get("contract_duration"), 200) if tr.get("contract_duration") else "",
                ]))
                jobs[sid] = Job(
                    source=NAME,
                    source_id=sid,
                    url=v.get("absolute_url") or v.get("short_url") or "",
                    title=tr.get("title", "").strip(),
                    organization=tr.get("organisation_name", ""),
                    location=v.get("city", "") or "",
                    description=desc,
                    deadline=iso_date(v.get("end_date")),
                    posted=iso_date(v.get("created_datetime") or v.get("start_date")),
                    extra={"salary": [v.get("min_salary"), v.get("max_salary")],
                           "keywords": v.get("keywords", [])},
                )
            if not r.get("next"):
                break
            offset += 100
    return list(jobs.values())
