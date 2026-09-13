"""Turn job locations (city names) into map coordinates, cached in data/geocode.json.

Uses OpenStreetMap's free Nominatim service for city names not seen before (max 1 request/second,
capped per run), so after the first run almost nothing needs looking up.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .sources.base import session

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "geocode.json"
MAX_LOOKUPS = 150
# Netherlands (incl. Wadden islands) bounding box: lon 3.2..7.3, lat 50.7..53.6
VIEWBOX = "3.2,53.6,7.3,50.7"


def norm_place(loc: str) -> str:
    """'6708 WD Wageningen, Gelderland' -> 'wageningen'."""
    s = re.sub(r"\b\d{4}\s?[A-Z]{2}\b", " ", loc or "")        # Dutch postcode
    s = s.split(",")[0].split(" / ")[0].split("|")[0]
    s = re.sub(r"(?i)\b(the\s+)?netherlands|nederland|\(.*?\)|hybrid|hybride|remote", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def load_cache() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def update(state: dict) -> dict:
    cache = load_cache()
    wanted = {norm_place(r.get("location", "")) for r in state.values() if r.get("active")}
    todo = [p for p in sorted(wanted) if p and len(p) > 1 and p not in cache][:MAX_LOOKUPS]
    for place in todo:
        try:
            r = session().get("https://nominatim.openstreetmap.org/search", timeout=20, params={
                "q": place, "countrycodes": "nl", "viewbox": VIEWBOX, "bounded": 1,
                "format": "json", "limit": 1,
            }, headers={"User-Agent": "nl-biology-job-scout (github.com/erezu1/efrat_jobs)"})
            r.raise_for_status()
            hits = r.json()
            cache[place] = [round(float(hits[0]["lat"]), 4), round(float(hits[0]["lon"]), 4)] if hits else None
        except Exception as e:
            print(f"geocode failed for {place!r}: {e}")
        time.sleep(1.1)
    if todo:
        print(f"geocoded {len(todo)} new places")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True))
    return cache
