"""Daily run: fetch all sources, prefilter, score with keyword rules, save state, render page.

Usage:  python -m jobscan.main [--only SOURCE ...]
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import re
import sys
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import scorer, sources
from .prefilter import EXCLUDE_TITLE, prefilter
from .render import dedupe_key
from .sources.base import Job

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "jobs.json"
RUNS = ROOT / "data" / "runs.json"
KEEP_CLOSED_DAYS = 45


def load_sources(only: list[str] | None):
    mods = []
    for info in pkgutil.iter_modules(sources.__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        if only and info.name not in only:
            continue
        mod = importlib.import_module(f"{sources.__name__}.{info.name}")
        if hasattr(mod, "fetch"):
            mods.append(mod)
    return mods


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader for local runs (KEY=value lines; .env is gitignored)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def expired(rec: dict, today: str) -> bool:
    """Deadline already passed, or the source flagged the ad as closed."""
    return bool((rec.get("extra") or {}).get("closed")
                or (rec.get("deadline") and rec["deadline"] < today))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="only run these source modules")
    args = ap.parse_args()
    load_dotenv()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = date.today().isoformat()
    state: dict[str, dict] = json.loads(STATE.read_text()) if STATE.exists() else {}
    run = {"time": now, "sources": {}, "new": 0, "scored": 0, "errors": []}

    # 1. Fetch
    known = {}   # dedupe key -> state key, to avoid re-fetching cross-posted ads
    for key, rec in state.items():
        dk = dedupe_key(rec["title"], rec.get("organization", ""))
        if dk:
            known.setdefault(dk, key)
    seen_now: set[str] = set()
    ok_sources: set[str] = set()
    for mod in load_sources(args.only):
        name = getattr(mod, "NAME", mod.__name__.rsplit(".", 1)[-1])
        t0 = time.time()
        try:
            jobs: list[Job] = mod.fetch()
        except Exception as e:
            run["sources"][name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
            run["errors"].append(name)
            print(f"[{name}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc()
            continue
        ok_sources.add(name)
        new = 0
        domain_specific = getattr(mod, "DOMAIN_SPECIFIC", False)
        for job in jobs:
            seen_now.add(job.key)
            rec = state.get(job.key)
            if rec is None:
                dk = dedupe_key(job.title, job.organization)
                twin = state.get(known.get(dk)) if dk else None
                if twin and len(twin.get("description", "")) > len(job.description):
                    # same ad already fetched from another site: reuse its text
                    job.description = twin["description"]
                    job.deadline = job.deadline or twin.get("deadline")
                elif hasattr(mod, "enrich") and not EXCLUDE_TITLE.search(job.title):
                    try:
                        job = mod.enrich(job)
                    except Exception as e:
                        print(f"[{name}] enrich failed for {job.url}: {e}", file=sys.stderr)
                if dk:
                    known.setdefault(dk, job.key)
                passes, reason = prefilter(job, domain_specific)
                rec = state[job.key] = {
                    **job.to_dict(), "first_seen": today,
                    "prefilter": {"pass": passes, "reason": reason},
                }
                new += 1
            else:
                # refresh listing fields that may change, keep enriched description
                for f in ("title", "organization", "location", "url"):
                    if getattr(job, f):
                        rec[f] = getattr(job, f)
                if job.deadline:
                    rec["deadline"] = job.deadline
            rec["last_seen"] = today
            rec["active"] = True
        run["sources"][name] = {"ok": True, "count": len(jobs), "new": new,
                                "seconds": round(time.time() - t0, 1)}
        run["new"] += new
        print(f"[{name}] {len(jobs)} jobs, {new} new ({time.time() - t0:.0f}s)")

    # 2. Mark closed (only for sources that fetched successfully) and prune old
    cutoff = (date.today() - timedelta(days=KEEP_CLOSED_DAYS)).isoformat()
    for key, rec in list(state.items()):
        if rec["source"] in ok_sources and key not in seen_now:
            rec["active"] = False
        if not rec.get("active") and rec.get("last_seen", today) < cutoff:
            del state[key]

    # 3. Score every active, prefiltered job (rules are cheap, so rule edits apply to all)
    for rec in state.values():
        rec.pop("score", None)
        if rec.get("active") and rec["prefilter"]["pass"] and not expired(rec, today):
            try:
                rec["score"] = scorer.score(Job(**{k: rec[k] for k in Job.__dataclass_fields__}))
                run["scored"] += 1
            except Exception as e:
                print(f"score failed for {rec['url']}: {e}", file=sys.stderr)
    print(f"scored {run['scored']} jobs")

    # 4. Save + render
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True))
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else []
    runs = (runs + [run])[-60:]
    RUNS.write_text(json.dumps(runs, indent=1))

    from .render import render
    render(state, runs, ROOT / "docs" / "index.html")
    from .notify import notify
    notify(state, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
