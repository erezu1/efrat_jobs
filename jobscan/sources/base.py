"""Shared types and HTTP helpers for job sources."""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field, asdict

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class Job:
    source: str               # short source name, e.g. "academictransfer"
    source_id: str            # id unique within the source (stable across runs)
    url: str                  # link to the ad
    title: str
    organization: str = ""
    location: str = ""
    description: str = ""     # plain text (HTML stripped), may be truncated
    deadline: str | None = None   # ISO date "YYYY-MM-DD" if known
    posted: str | None = None     # ISO date "YYYY-MM-DD" if known
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return asdict(self)


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
        })
    return _session


def get(url: str, *, params=None, headers=None, retries: int = 2, timeout: int = 30) -> requests.Response:
    """GET with small retry/backoff. Raises on final failure."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = session().get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def html_to_text(s: str | None, limit: int = 8000) -> str:
    if not s:
        return ""
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"(?s)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s[:limit]


def iso_date(s: str | None) -> str | None:
    """Return the YYYY-MM-DD prefix of an ISO-ish timestamp, else None."""
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None
