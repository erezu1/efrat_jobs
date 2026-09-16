"""Rewrite the scan's caches as the union of their versions in the given git refs and on disk.

The caches are JSON maps keyed by a hash of the source text, so the union of any two versions is
always correct. A line-based git merge is not: with one entry per line it can drop entries or
leave the file invalid. The daily workflow runs this after rebasing onto whatever landed while it
was scanning, so no translation or geocode is ever lost.

Usage: python tools/merge_caches.py REF [REF ...]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHES = ["data/translations.json", "data/fulltext_en.json", "data/geocode.json"]


def at(ref: str, path: str) -> dict:
    out = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True, text=True)
    try:
        return json.loads(out.stdout) if out.returncode == 0 else {}
    except json.JSONDecodeError:
        return {}


def main(refs: list[str]) -> None:
    for path in CACHES:
        merged: dict = {}
        for ref in refs:
            merged.update(at(ref, path))
        try:
            merged.update(json.loads((ROOT / path).read_text()))
        except (FileNotFoundError, json.JSONDecodeError):
            pass                                        # a merge left it broken: the refs have it all
        if merged:
            (ROOT / path).write_text(json.dumps(merged, ensure_ascii=False, indent=0, sort_keys=True))
            print(f"{path}: {len(merged)} entries")


if __name__ == "__main__":
    main(sys.argv[1:])
