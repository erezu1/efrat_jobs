"""Render the static dashboard (docs/index.html) from saved state."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from . import geocode


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())


_PHD = re.compile(r"(?i)\bph\.?d\b|promovend|doctoral\s+candidate|doctoraal")
_TECH = re.compile(r"(?i)technician|technicus|analist|analyst|laborant|research\s+assistant|"
                   r"onderzoeksassistent|lab\b|laborator|junior\s+researcher|onderzoeker|researcher")
_NATURE_SOURCES = {"nature_employers", "greenjobs", "sustainablejobs", "fondsen", "groeneruimte"}
_INDUSTRY_SOURCES = {"industry", "wageningen_companies"}


def guess_category(title: str, source: str) -> str | None:
    """Rough job-type label from the title/source, used until Claude has scored the job."""
    if _PHD.search(title):
        return "phd"
    if source in _NATURE_SOURCES:
        return "conservation_zoo_ngo"
    if source in _INDUSTRY_SOURCES:
        return "industry"
    if _TECH.search(title):
        return "technician_research"
    return None


def dedupe_key(title: str, org: str, deadline: str | None = None) -> str | None:
    """Key for spotting the same ad on several sites. Long titles are distinctive on their
    own (orgs are often spelled differently across boards); shorter ones also need the same
    deadline, or else the same organization."""
    nt = _norm(title)
    if len(nt) >= 25:
        return nt
    if deadline and len(nt) >= 12:
        return f"{nt}#{deadline}"
    no = _norm(org)
    return f"{nt}@{no}" if nt and no else None


def build_rows(state: dict) -> list[dict]:
    rows, by_title = [], {}
    today = date.today().isoformat()
    # best copy first, so cross-posted duplicates merge into the scored/prefiltered one
    ordered = sorted(state.items(), key=lambda kv: (
        not kv[1]["prefilter"]["pass"], -((kv[1].get("score") or {}).get("fit_score") or -1)))
    for key, r in ordered:
        if not r.get("active") or (r.get("extra") or {}).get("closed"):
            continue
        s = r.get("score") or {}
        if (r.get("deadline") or s.get("deadline") or "9999") < today:
            continue
        row = {
            "key": key, "title": r["title"], "org": r.get("organization", ""),
            "loc": r.get("location", ""), "url": r["url"], "source": r["source"],
            "first_seen": r.get("first_seen"),
            "deadline": r.get("deadline") or s.get("deadline"),
            "pre": r["prefilter"]["pass"], "pre_reason": r["prefilter"]["reason"],
            "score": s.get("fit_score"),
            "cat": s.get("category") or guess_category(r["title"], r["source"]),
            "summary": s.get("summary", ""),
            "why": s.get("why", ""), "blockers": s.get("blockers", []),
            "dutch": s.get("dutch_required"), "nl": s.get("in_netherlands", True),
            "also": [],
        }
        dk = dedupe_key(row["title"], row["org"], row["deadline"])
        if dk and dk in by_title:   # cross-posted duplicate: merge
            first = by_title[dk]
            first["also"].append({"source": row["source"], "url": row["url"]})
            first["deadline"] = first["deadline"] or row["deadline"]
            continue
        if dk:
            by_title[dk] = row
        rows.append(row)
    return rows


def render(state: dict, runs: list[dict], out: Path) -> None:
    rows = build_rows(state)
    coords = geocode.load_cache()
    for row in rows:
        row["ll"] = coords.get(geocode.norm_place(row["loc"]))
    last = runs[-1] if runs else {}
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "rows": rows,
        "sources": last.get("sources", {}),
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE.replace("__DATA__", data))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<link rel="manifest" href="app.webmanifest">
<meta name="application-name" content="BioJobs">
<meta name="apple-mobile-web-app-title" content="BioJobs">
<meta name="theme-color" content="#7b2d8e">
<meta name="mobile-web-app-capable" content="yes">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<title>BioJobs</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%237b2d8e'/><stop offset='1' stop-color='%23d6409f'/></linearGradient></defs><rect width='64' height='64' rx='16' fill='url(%23g)'/><g fill='none' stroke='white' stroke-width='4.5' stroke-linecap='round'><path d='M21 10C21 23 43 23 43 32S21 41 21 54'/><path d='M43 10C43 23 21 23 21 32S43 41 43 54'/></g><g stroke='white' stroke-width='3' stroke-linecap='round' opacity='.8'><path d='M25 15h14M25 49h14M29 22h6M29 42h6'/></g></svg>">
<style>
:root{
  --bg:#f7f3f8; --panel:#fff; --ink:#241a28; --muted:#6f6474; --line:#e8dfeb;
  --accent:#7b2d8e; --accent-soft:#f4e5f5; --warn:#b4541a; --warn-soft:#fbeadf;
  --danger:#b3261e; --chip:#f0e8f2;
  --s-hi:#7b2d8e; --s-mid:#c2378a; --s-lo:#a79cab;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#151117; --panel:#201a23; --ink:#ece6ee; --muted:#a397a8; --line:#352c39;
    --accent:#d59ce6; --accent-soft:#3b2543; --warn:#e89a5f; --warn-soft:#3a2a1e; --danger:#ef7a70;
    --chip:#2b2430; --s-hi:#d59ce6; --s-mid:#f08cc0; --s-lo:#7a6f7f;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
header{padding:28px 20px 8px;max-width:980px;margin:0 auto}
h1{margin:0;font-size:24px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 4px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 14px;cursor:pointer;min-width:120px}
.stat b{display:block;font-size:22px;line-height:1.2}
.stat span{color:var(--muted);font-size:12px}
.stat.on{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
main{max-width:980px;margin:0 auto;padding:0 20px 60px}
.controls{position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--line)}
input[type=search]{flex:1 1 220px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);font:inherit}
select,button{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);cursor:pointer}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{padding:5px 10px;border-radius:999px;background:var(--chip);border:1px solid transparent;font-size:13px;cursor:pointer;user-select:none}
.chip.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
label.tog{font-size:13px;color:var(--muted);display:flex;gap:5px;align-items:center}
.count{color:var(--muted);font-size:13px;margin:12px 0 4px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0;display:grid;grid-template-columns:52px 1fr;gap:14px}
.card.dim{opacity:.55}
.card>div{min-width:0}
.title,.summary,.why{overflow-wrap:anywhere}
.tags{min-width:0}
.tag{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.score{width:52px;height:52px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:20px;color:#fff}
.score.na{background:var(--chip);color:var(--muted);font-size:14px}
.title{font-weight:600;font-size:16px;color:var(--ink);text-decoration:none}
.title:hover{color:var(--accent);text-decoration:underline}
.meta{color:var(--muted);font-size:13px;margin-top:2px;display:flex;gap:10px;flex-wrap:wrap}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.tag{font-size:12px;padding:2px 8px;border-radius:6px;background:var(--chip);color:var(--muted)}
.tag.new{background:var(--accent-soft);color:var(--accent);font-weight:600}
.tag.dl{background:var(--warn-soft);color:var(--warn);font-weight:600}
.tag.urgent{background:var(--danger);color:#fff}
.summary{margin:8px 0 0}
.why{color:var(--muted);font-size:14px;margin:4px 0 0}
.blockers{color:var(--danger);font-size:13px;margin:4px 0 0}
.actions{display:flex;gap:6px;margin-top:10px}
.actions button{font-size:12px;padding:3px 9px}
.actions button.on{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
details.srcs{margin-top:30px;color:var(--muted);font-size:13px}
details.srcs table{border-collapse:collapse;margin-top:8px}
details.srcs td{padding:2px 12px 2px 0}
.bad{color:var(--danger)}
.empty{padding:40px;text-align:center;color:var(--muted)}
.notice{margin:12px 0 0;padding:10px 14px;border-radius:10px;background:var(--warn-soft);color:var(--warn);font-size:13px}
[hidden]{display:none!important}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{border:0;border-radius:0;padding:7px 12px}
.seg button.on{background:var(--accent);color:#fff}
#map{height:min(70vh,640px);border-radius:12px;border:1px solid var(--line);margin-top:10px;z-index:1}
.pop{max-height:260px;overflow:auto;font-size:13px;min-width:220px}
.pop h4{margin:0 0 6px;font-size:14px}
.pop div{margin:5px 0}
.pop b{display:inline-block;min-width:22px;text-align:center;border-radius:5px;color:#fff;margin-right:5px}
.nomap{color:var(--muted);font-size:12px;margin-top:6px}

/* --- Material-style elevation & icons (visual only) --- */
:root{
  --e1:0 1px 2px rgba(40,20,45,.10),0 1px 3px 1px rgba(40,20,45,.06);
  --e2:0 1px 2px rgba(40,20,45,.12),0 2px 6px 2px rgba(40,20,45,.08);
  --e3:0 4px 8px 3px rgba(40,20,45,.10),0 1px 3px rgba(40,20,45,.14);
  --bg:#f7f3f8;
}
@media (prefers-color-scheme: dark){
  :root{--e1:0 1px 2px rgba(0,0,0,.5),0 1px 3px 1px rgba(0,0,0,.3);
        --e2:0 1px 2px rgba(0,0,0,.5),0 2px 6px 2px rgba(0,0,0,.35);
        --e3:0 4px 8px 3px rgba(0,0,0,.4),0 1px 3px rgba(0,0,0,.5); --bg:#130f15;}
}
.mi{font-family:"Material Symbols Rounded";font-weight:normal;font-style:normal;font-size:20px;line-height:1;
  display:inline-block;vertical-align:middle;letter-spacing:normal;text-transform:none;white-space:nowrap;
  -webkit-font-feature-settings:"liga";font-feature-settings:"liga";font-variation-settings:"FILL" 0,"wght" 400,"GRAD" 0,"opsz" 20}
.mi.fill{font-variation-settings:"FILL" 1,"wght" 400,"GRAD" 0,"opsz" 20}
h1{display:flex;align-items:center;gap:12px;font-family:"Sora",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-weight:800;font-size:28px;letter-spacing:-.03em;line-height:1}
h1 .name{background:linear-gradient(135deg,#7b2d8e,#d6409f);-webkit-background-clip:text;background-clip:text;color:transparent}
@media (prefers-color-scheme: dark){h1 .name{background-image:linear-gradient(135deg,#d59ce6,#f08cc0)}}
h1 .logo{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#7b2d8e,#d6409f);color:#fff;display:flex;align-items:center;justify-content:center;box-shadow:var(--e2)}
.helix{width:100%;height:100%;display:block}
.stat{border:0;border-radius:16px;padding:12px 16px;box-shadow:var(--e1);transition:box-shadow .2s,transform .2s}
.stat:hover{box-shadow:var(--e3);transform:translateY(-1px)}
.stat.on{background:var(--accent);color:var(--on-accent);box-shadow:var(--e2)}
.stat.on span{color:var(--on-accent);opacity:.85}
:root{--on-accent:#fff}
@media (prefers-color-scheme: dark){:root{--on-accent:#1f0f26}}
.controls{border-bottom:0;background:transparent;padding-top:max(12px,env(safe-area-inset-top))}
/* full-width backing behind the pinned bar (so card shadows never peek out at the sides) */
.controls::before{content:"";position:absolute;top:0;bottom:0;left:-50vw;right:-50vw;background:var(--bg);z-index:-1;
  transition:background .25s}
html,body{overflow-x:clip}
/* once pinned: frosted glass — translucent + blur, extending below the bar and fading out smoothly.
   The blur lives on this pseudo-layer, not on the sticky element itself (safer on Android Chrome). */
@supports ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .controls.stuck::before{bottom:-34px;background:color-mix(in srgb,var(--bg) 68%,transparent);
    -webkit-backdrop-filter:blur(16px) saturate(1.5);backdrop-filter:blur(16px) saturate(1.5);
    -webkit-mask-image:linear-gradient(to bottom,#000 0,#000 calc(100% - 34px),transparent 100%);
    mask-image:linear-gradient(to bottom,#000 0,#000 calc(100% - 34px),transparent 100%)}
}
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .controls::after{content:"";position:absolute;left:-50vw;right:-50vw;top:100%;height:28px;pointer-events:none;
    background:linear-gradient(to bottom,var(--bg),transparent);opacity:0;transition:opacity .25s}
  .controls.stuck::after{opacity:1}
}
input[type=search],select{border:0;border-radius:12px;box-shadow:var(--e1);padding:9px 12px}
input[type=search]:focus,select:focus{outline:2px solid var(--accent);outline-offset:0}
.chip{border:0;box-shadow:var(--e1);background:var(--panel);padding:6px 12px;transition:box-shadow .15s}
.chip:hover{box-shadow:var(--e2)}
.chip.on{background:var(--accent-soft);color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.card{border:0;border-radius:16px;box-shadow:var(--e1);transition:box-shadow .2s;padding:16px 18px}
.card:hover{box-shadow:var(--e3)}
.score{border-radius:14px;box-shadow:var(--e1)}
.tag{border-radius:8px;display:inline-flex;align-items:center;gap:3px}
.tag .mi{font-size:15px}
.meta .mi{font-size:16px;margin-right:2px;vertical-align:-3px}
.blockers .mi{font-size:17px;vertical-align:-3px}
.actions button{border:0;border-radius:999px;padding:5px 12px 5px 9px;background:var(--chip);display:inline-flex;align-items:center;gap:4px;transition:box-shadow .15s,background .15s}
.actions{align-items:center;justify-content:center;gap:12px;margin-top:14px}
.actions .vote{width:48px;height:48px;padding:0;justify-content:center;border-radius:50%;transition:transform .15s,background .15s,box-shadow .15s}
.actions .vote .mi{font-size:28px;font-variation-settings:"FILL" 0,"wght" 600,"GRAD" 0,"opsz" 24}
.actions .vote.on{box-shadow:var(--e2)}

.applybox{display:inline-flex;align-items:center;gap:4px;margin-left:4px;padding:6px 12px 6px 9px;border-radius:999px;background:var(--chip);font-size:13px;cursor:pointer;user-select:none}
.applybox input{display:none}
.applybox .mi{font-size:18px}
.applybox.on{background:var(--accent-soft);color:var(--accent);font-weight:600}
.card{position:relative;touch-action:pan-y;cursor:pointer}
.card:active{transform:scale(.995)}
.card.liked{box-shadow:var(--e1),inset 4px 0 0 var(--accent)}
.card.dragging{user-select:none;cursor:grabbing;z-index:2}
@property --p{syntax:"<number>";inherits:true;initial-value:0}
/* swipe feedback scales continuously with drag progress --p (0..1) */
.card::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:calc(var(--p) * .92);
  background:color-mix(in srgb,var(--panel) 62%,transparent)}
.card[data-dir="yes"]::after{background:linear-gradient(to right,color-mix(in srgb,var(--accent) 26%,var(--panel)) 0%,color-mix(in srgb,var(--panel) 60%,transparent) 70%)}
.card[data-dir="no"]::after{background:linear-gradient(to left,color-mix(in srgb,var(--danger) 22%,var(--panel)) 0%,color-mix(in srgb,var(--panel) 60%,transparent) 70%)}
.card::after{z-index:2}
.card .actions{position:relative;z-index:3}
.toast{position:fixed;left:50%;bottom:max(20px,env(safe-area-inset-bottom));z-index:50;display:flex;align-items:center;gap:10px;
  background:#2a2030;color:#fff;border-radius:14px;padding:10px 10px 10px 16px;box-shadow:0 8px 28px rgba(20,10,25,.35);
  font-size:14px;width:max-content;max-width:calc(100vw - 28px);transform:translate(-50%,24px);opacity:0;transition:transform .25s ease,opacity .25s ease}
.toast.in{transform:translate(-50%,0);opacity:1}
.toast .mi{font-size:20px;color:#f08cc0}
.toast .msg{white-space:nowrap}
.toast button{border:0;border-radius:10px;background:transparent;color:#f08cc0;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:8px 12px;font-size:13px}
.toast button:hover{background:rgba(255,255,255,.08)}
@media (prefers-color-scheme: dark){.toast{background:#ece6ee;color:#241a28}.toast .mi,.toast button{color:#7b2d8e}}
header{position:relative}
.toph{display:flex;align-items:center;justify-content:space-between;gap:12px}
.iconbtn.syncbtn{display:inline-flex;flex:none;width:42px;height:42px;border-radius:14px;background:var(--panel)}
.iconbtn.syncbtn .mi{font-size:22px}
.syncbtn.on{background:var(--panel);color:var(--accent)}
.syncpanel{position:absolute;right:20px;top:72px;z-index:40;width:min(340px,calc(100vw - 28px));background:var(--panel);border-radius:18px;box-shadow:var(--e3);padding:14px 16px;font-size:14px}
.syncpanel .head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.syncpanel .x{border:0;background:transparent;padding:4px;border-radius:8px}
.syncpanel p{margin:6px 0}
.syncpanel p .mi{font-size:18px;vertical-align:-4px;color:var(--accent)}
.syncpanel .small{color:var(--muted);font-size:12.5px}
.syncpanel .err{color:var(--danger);font-size:13px}
.syncpanel input{width:100%;border:0;border-radius:10px;box-shadow:var(--e1);padding:9px 11px;font:inherit;margin:6px 0;background:var(--bg);color:var(--ink)}
.syncpanel .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.syncpanel .row button{border:0;border-radius:999px;padding:7px 14px;background:var(--chip);display:inline-flex;align-items:center;gap:5px;font-size:13px}
.syncpanel .row button.primary{background:linear-gradient(135deg,#7b2d8e,#d6409f);color:#fff}
.syncpanel .row button .mi{font-size:17px}
@media (max-width:760px){.syncpanel{right:14px;top:62px}}
.swipebadge{position:absolute;top:50%;z-index:3;width:84px;height:84px;margin-top:-42px;border-radius:50%;pointer-events:none;
  display:flex;align-items:center;justify-content:center;color:#fff;box-shadow:0 8px 24px rgba(40,20,45,.35);opacity:0;transform:scale(.3)}
.swipebadge .mi{font-size:54px;font-variation-settings:"FILL" 1,"wght" 700,"GRAD" 0,"opsz" 48}
.swipebadge.yes{left:24px;background:linear-gradient(135deg,#7b2d8e,#d6409f)}
.swipebadge.no{right:24px;background:var(--danger)}
.vote{position:relative;overflow:hidden}
.vote .fill{position:absolute;inset:0;border-radius:50%;opacity:0;pointer-events:none}
.vote.yes .fill{background:linear-gradient(135deg,#7b2d8e,#d6409f)}
.vote.no .fill{background:var(--danger)}
.vote .mi{position:relative}
.vote.on .fill{opacity:1}
.vote.on .mi{color:#fff}
.actions button:hover{box-shadow:var(--e1)}
.actions button .mi{font-size:18px}

.seg{border:0;border-radius:999px;box-shadow:var(--e1);background:var(--panel);padding:3px}
.seg button{border-radius:999px;display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:transparent}
.seg button.on{background:var(--accent);color:#fff;box-shadow:var(--e1)}
#map{border:0;border-radius:16px;box-shadow:var(--e2)}
.notice{box-shadow:var(--e1);border-radius:12px}
details.srcs{background:var(--panel);border-radius:16px;box-shadow:var(--e1);padding:12px 16px}
.placelink{color:inherit;text-decoration:none;border-radius:6px;padding:0 3px;margin:0 -3px}
.cattag{text-decoration:none;cursor:pointer}
.cattag:hover{background:var(--accent-soft);color:var(--accent)}
.placelink:hover{color:var(--accent);background:var(--accent-soft)}
.placechip{display:inline-flex;align-items:center;gap:4px}
.placechip .mi{font-size:16px}
.onlyhere{margin:2px 0 6px;border:0;border-radius:999px;background:var(--accent);color:#fff;padding:4px 10px 4px 7px;font-size:12px;display:inline-flex;align-items:center;gap:3px;cursor:pointer}
.onlyhere .mi{font-size:16px}
.minilogo{width:0;height:38px;border-radius:12px;background:linear-gradient(135deg,#7b2d8e,#d6409f);color:#fff;
  display:flex;align-items:center;justify-content:center;overflow:hidden;opacity:0;margin-right:-8px;
  transition:width .2s,opacity .2s,margin .2s;box-shadow:var(--e1);text-decoration:none;flex:none}
.minilogo .mi{font-size:22px}
.controls.stuck .minilogo{width:38px;opacity:1;margin-right:0}
.controls{row-gap:8px}
.ctlrow{flex-basis:100%;display:flex;justify-content:space-between;align-items:center;gap:8px}
.ctlrow .left{display:flex;align-items:center;gap:6px;flex-wrap:wrap;min-width:0}
.toprow{flex-basis:100%;display:flex;gap:8px;align-items:center}
.toprow input[type=search]{flex:1 1 auto;min-width:0}
.filters{flex-basis:100%}
.filters-inner{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.iconbtn{position:relative;border:0;border-radius:12px;box-shadow:var(--e1);width:40px;height:38px;padding:0;display:none;align-items:center;justify-content:center;flex:none}
.iconbtn.on{background:var(--accent);color:var(--on-accent)}
.fdot{position:absolute;top:6px;right:7px;width:8px;height:8px;border-radius:50%;background:#d6409f;box-shadow:0 0 0 2px var(--panel)}
.fchip{display:inline-flex;align-items:center;gap:3px;font-size:12px;padding:3px 8px}
.fchip .mi{font-size:15px}
@media (max-width: 760px){
  header{padding:18px 14px 4px}
  main{padding:0 14px 60px}
  .sub{font-size:12px}
  .stats{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin:12px -14px 4px;padding:4px 14px 8px;gap:8px}
  .stats::-webkit-scrollbar{display:none}
  .stat{min-width:auto;flex:none;padding:8px 12px}
  .stat b{font-size:18px}
  .iconbtn{display:inline-flex}
  /* collapsible filter panel: grid rows 0fr→1fr animates the real height, so open/close is continuous */
  .filters{display:grid;grid-template-rows:0fr;margin-top:-8px;opacity:0;pointer-events:none;
    transition:grid-template-rows .34s cubic-bezier(.4,0,.2,1),margin-top .34s cubic-bezier(.4,0,.2,1),opacity .26s ease}
  .filters-inner{min-height:0;overflow:hidden;transform:translateY(-8px);transition:transform .34s cubic-bezier(.4,0,.2,1)}
  .filters.open{grid-template-rows:1fr;margin-top:0;opacity:1;pointer-events:auto}
  .filters.open .filters-inner{transform:none;padding:4px 0 2px}
  .filters-inner select{flex:1 1 30%}
  .iconbtn .mi{transition:transform .32s cubic-bezier(.2,.8,.2,1)}
  #btnFilters.on .mi{transform:rotate(90deg)}
  .card{grid-template-columns:40px minmax(0,1fr);gap:10px;padding:14px}
  .meta{gap:4px 10px}
  .actions{flex-wrap:wrap}
  .score{width:40px;height:40px;font-size:17px;border-radius:12px}
  .seg button{padding:5px 10px}
}
.ctlrow .count{margin:0}
@media (prefers-color-scheme: dark){
  .leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.9) contrast(.9) saturate(.6)}
  .leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--panel);color:var(--ink)}
  .leaflet-popup-content a{color:var(--accent)}
  .leaflet-bar a{background:var(--panel);color:var(--ink);border-color:var(--line)}
  .leaflet-control-attribution{background:rgba(0,0,0,.5)!important;color:#bbb}
  .leaflet-control-attribution a{color:#ddd}
}
.leaflet-popup-content-wrapper{border-radius:14px;box-shadow:var(--e3)}
</style>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@700;800&display=swap">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0..1,0&display=block">
</head>
<body>
<header>
  <div class="toph">
    <h1><span class="logo"><svg class="helix" viewBox="0 0 64 64" aria-hidden="true"><g fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round"><path d="M21 10C21 23 43 23 43 32S21 41 21 54"/><path d="M43 10C43 23 21 23 21 32S43 41 43 54"/></g><g stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".8"><path d="M25 15h14M25 49h14M29 22h6M29 42h6"/></g></svg></span><span class="name">BioJobs</span></h1>
    <button class="iconbtn syncbtn" id="syncbtn" title="Sync marks across devices"><span class="mi">cloud_off</span></button>
  </div>
  <div class="stats" id="stats"></div>
  <div class="syncpanel" id="syncpanel" hidden>
    <div class="head"><b>Sync across devices</b><button class="x" id="syncclose" aria-label="Close"><span class="mi">close</span></button></div>
    <div class="body"></div>
  </div>
</header>
<main>
  <div class="controls" id="controls">
    <div class="toprow">
      <a class="minilogo" href="#" id="minilogo" title="Back to top"><svg class="helix" viewBox="0 0 64 64" aria-hidden="true"><g fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round"><path d="M21 10C21 23 43 23 43 32S21 41 21 54"/><path d="M43 10C43 23 21 23 21 32S43 41 43 54"/></g><g stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".8"><path d="M25 15h14M25 49h14M29 22h6M29 42h6"/></g></svg></a>
      <input type="search" id="q" placeholder="Search jobs…">
      <button class="iconbtn" id="btnFilters" title="Filters" aria-expanded="false"><span class="mi">tune</span><span class="fdot" id="fdot" hidden></span></button>
    </div>
    <div class="filters" id="filters">
      <div class="filters-inner">
        <select id="type" title="Job type"><option value="">All job types</option></select>
        <select id="minscore" title="Minimum fit score">
          <option value="7">Score ≥ 7</option><option value="5" selected>Score ≥ 5</option>
          <option value="3">Score ≥ 3</option><option value="0">All scores</option>
        </select>
        <select id="sort" title="Sort"><option value="score">Best fit</option><option value="deadline">Deadline</option><option value="new">Newest</option></select>
        <label class="tog"><input type="checkbox" id="showhidden"> show dismissed</label>
        <label class="tog"><input type="checkbox" id="showfiltered"> show keyword-filtered</label>
      </div>
    </div>
    <div class="ctlrow">
      <div class="left">
        <div class="count" id="count"></div>
        <span class="chip on fchip" id="typechip" hidden><span id="typename"></span><span class="mi">close</span></span>
        <span class="chip on fchip placechip" id="placechip" hidden><span class="mi">location_on</span><span id="placename"></span><span class="mi">close</span></span>
      </div>
      <div class="seg"><button id="btnList" class="on"><span class="mi">view_agenda</span>List</button><button id="btnMap"><span class="mi">map</span>Map</button></div>
    </div>
  </div>
  <div class="notice" id="unscored" hidden>Some jobs have no score yet. They'll be scored on the next daily run.</div>
  <div id="map" hidden></div>
  <div class="nomap" id="nomap" hidden></div>
  <div id="list"></div>
  <div class="toast" id="toast" hidden role="status"><span class="mi">block</span><span class="msg"></span><button>Undo</button></div>
  <details class="srcs"><summary>Sources in the last run · <span id="gen"></span></summary><table id="srcs"></table></details>
</main>
<script>
const DATA = __DATA__;
const CATS = {phd:"PhD", technician_research:"Research & lab", conservation_zoo_ngo:"Nature & zoos", industry:"Industry", other:"Other"};
const DUTCH = {basic:"Dutch: basic", fluent:"Dutch: fluent required"};
const today = new Date(); today.setHours(0,0,0,0);
const daysTo = d => d ? Math.round((new Date(d+"T00:00:00") - today)/864e5) : null;
const daysSince = d => d ? Math.round((today - new Date(d+"T00:00:00"))/864e5) : 999;

// marks[key] = "interested" | "hidden" (not interested) — mutually exclusive; applied[key] = true
let marks = {}, applied = {};
try { marks = JSON.parse(localStorage.getItem("marks") || "{}"); } catch(e) {}
try { applied = JSON.parse(localStorage.getItem("applied") || "{}"); } catch(e) {}
for (const [k, m] of Object.entries(marks)) {          // migrate older "saved"/"applied" marks
  if (m === "saved") marks[k] = "interested";
  if (m === "applied") { marks[k] = "interested"; applied[k] = true; }
}
// stamps[key] = when this job's mark last changed (ms) — lets devices merge: newest change wins
let stamps = {};
try { stamps = JSON.parse(localStorage.getItem("stamps") || "{}"); } catch(e) {}
const saveMarks = (changedKey) => {
  if (changedKey) stamps[changedKey] = Date.now();
  try {
    localStorage.setItem("marks", JSON.stringify(marks)); localStorage.setItem("applied", JSON.stringify(applied));
    localStorage.setItem("stamps", JSON.stringify(stamps));
  } catch(e) {}
  if (changedKey) Sync.schedulePush();
};
function setMark(k, m, force = false){   // tap toggles; swipe (force) always sets
  const before = {mark: marks[k], applied: !!applied[k]};
  if (!force && marks[k] === m) delete marks[k]; else marks[k] = m;
  if (marks[k] !== "interested") delete applied[k];
  saveMarks(k); draw();
  if (marks[k] === "hidden" && before.mark !== "hidden") showUndo(k, before);
}

// ---------- Sync marks across devices via a private GitHub Gist ----------
// The token is entered on each device (or arrives via a private "connect" link) and is kept only in
// that browser's storage — it is never part of this public page.
const Sync = (() => {
  const FILE = "biojobs-marks.json", DESC = "BioJobs sync (marks)";
  let cfg = null, pushTimer = null, busy = false, lastSync = null, lastError = "";
  try { cfg = JSON.parse(localStorage.getItem("sync") || "null"); } catch(e) {}
  const api = (path, opts = {}) => fetch("https://api.github.com" + path, {...opts, cache: "no-store",
    headers: {"Authorization": "Bearer " + cfg.token, "Accept": "application/vnd.github+json", ...(opts.headers || {})}})
    .then(async r => { if (!r.ok) throw new Error(`GitHub ${r.status}`); return r.status === 204 ? null : r.json(); });
  const snapshot = () => {
    const keys = new Set([...Object.keys(marks), ...Object.keys(applied), ...Object.keys(stamps)]);
    const out = {};
    keys.forEach(k => out[k] = {m: marks[k] || null, a: !!applied[k], t: stamps[k] || 1});
    return out;
  };
  const merge = remote => {       // newest change per job wins; returns true if local has newer data
    let localNewer = false, changed = false;
    const local = snapshot();
    for (const [k, r] of Object.entries(remote || {})) {
      const l = local[k];
      if (!l || r.t > l.t) {
        if (r.m) marks[k] = r.m; else delete marks[k];
        if (r.a) applied[k] = true; else delete applied[k];
        stamps[k] = r.t; changed = true;
      } else if (l.t > r.t) localNewer = true;
    }
    for (const k of Object.keys(local)) if (!(k in (remote || {}))) localNewer = true;
    if (changed) { saveMarks(); draw(); }
    return localNewer;
  };
  async function pull(){
    if (!cfg || busy) return;
    busy = true; status("syncing");
    try {
      const g = await api(`/gists/${cfg.gist}`);
      let remote = {};
      try { remote = JSON.parse(g.files?.[FILE]?.content || "{}"); } catch(e) {}
      if (merge(remote)) await push(true);
      lastSync = new Date(); lastError = "";
    } catch(e) { lastError = e.message; }
    busy = false; status();
  }
  async function push(inner = false){
    if (!cfg || (busy && !inner)) return;
    if (!inner) { busy = true; status("syncing"); }
    try {
      await api(`/gists/${cfg.gist}`, {method: "PATCH",
        body: JSON.stringify({files: {[FILE]: {content: JSON.stringify(snapshot())}}})});
      lastSync = new Date(); lastError = "";
    } catch(e) { lastError = e.message; }
    if (!inner) { busy = false; status(); }
  }
  function schedulePush(){ if (!cfg) return; clearTimeout(pushTimer); pushTimer = setTimeout(() => pull(), 1200); }
  async function connect(token, gistId){
    cfg = {token: token.trim(), gist: gistId || null};
    try {
      if (!cfg.gist) {        // find this user's existing BioJobs gist, or create one
        const mine = await api("/gists?per_page=100");
        const found = mine.find(g => g.description === DESC);
        cfg.gist = found ? found.id : (await api("/gists", {method: "POST",
          body: JSON.stringify({description: DESC, public: false, files: {[FILE]: {content: "{}"}}})})).id;
      }
      localStorage.setItem("sync", JSON.stringify(cfg));
      await pull();
      if (lastError) throw new Error(lastError);
      return true;
    } catch(e) { cfg = null; localStorage.removeItem("sync"); lastError = e.message; status(); return false; }
  }
  function disconnect(){ cfg = null; localStorage.removeItem("sync"); status(); }
  const link = () => cfg ? `${location.origin}${location.pathname}#sync=${btoa(JSON.stringify(cfg))}` : "";
  function status(state){
    const b = $("syncbtn"); if (!b) return;
    const icon = !cfg ? "cloud_off" : state === "syncing" ? "cloud_sync" : lastError ? "cloud_alert" : "cloud_done";
    b.querySelector(".mi").textContent = icon;
    b.classList.toggle("on", !!cfg && !lastError);
    b.title = !cfg ? "Sync marks across devices" : lastError ? `Sync problem: ${lastError}` : "Synced across devices";
    renderSyncPanel();
  }
  function renderSyncPanel(){
    const d = $("syncpanel"); if (!d || d.hidden) return;
    d.querySelector(".body").innerHTML = !cfg ? `
      <p>Marks (Interested / Applied / Rejected) are saved in this browser only. Connect to keep them in sync on all your devices.</p>
      <p class="small">Use a GitHub token that can only access <b>Gists</b>. It stays on this device.</p>
      <input id="synctoken" type="password" placeholder="GitHub token (github_pat_…)" autocomplete="off">
      ${lastError ? `<p class="err">${esc(lastError)} — check the token.</p>` : ""}
      <div class="row"><button class="primary" id="syncconnect">Connect</button></div>` : `
      <p><span class="mi">${lastError ? "cloud_alert" : "cloud_done"}</span> ${lastError ? "Sync problem: " + esc(lastError) :
        "Synced" + (lastSync ? " · " + lastSync.toLocaleTimeString() : "")}</p>
      <p class="small">To connect another device, open this link on it. Share it privately; it contains the sync key.</p>
      <div class="row"><button class="primary" id="synccopy"><span class="mi">link</span>Copy link for another device</button></div>
      <div class="row"><button id="syncnow"><span class="mi">sync</span>Sync now</button><button id="syncoff">Disconnect this device</button></div>`;
    const on = (id, f) => { const el = $(id); if (el) el.onclick = f; };
    on("syncconnect", async () => { const t = $("synctoken").value; if (t) { $("syncconnect").textContent = "Connecting…"; await connect(t); } });
    on("synccopy", async () => {
      try { await navigator.clipboard.writeText(link()); $("synccopy").innerHTML = '<span class="mi">check</span>Copied'; }
      catch(e) { prompt("Copy this link:", link()); }
    });
    on("syncnow", () => pull());
    on("syncoff", () => disconnect());
  }
  function init(){
    const m = location.hash.match(/#sync=([^&]+)/);     // arrived via a "connect this device" link
    if (m) {
      history.replaceState(null, "", location.pathname + location.search);
      try { const c = JSON.parse(atob(decodeURIComponent(m[1]))); if (c.token && c.gist) connect(c.token, c.gist); } catch(e) {}
    }
    $("syncbtn").onclick = () => { const d = $("syncpanel"); d.hidden = !d.hidden; renderSyncPanel(); };
    $("syncclose").onclick = () => { $("syncpanel").hidden = true; };
    status();
    if (cfg) pull();
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") pull(); });
    setInterval(() => { if (document.visibilityState === "visible") pull(); }, 60000);
  }
  return {init, schedulePush, pull};
})();
let undoTimer = null;
function showUndo(k, before){
  const t = $("toast");
  t.querySelector(".msg").textContent = "Marked not interested";
  t.querySelector("button").onclick = () => {
    if (before.mark) marks[k] = before.mark; else delete marks[k];
    if (before.applied) applied[k] = true; else delete applied[k];
    saveMarks(k); hideUndo(); draw();
  };
  t.classList.remove("out"); t.hidden = false;
  requestAnimationFrame(() => t.classList.add("in"));
  clearTimeout(undoTimer); undoTimer = setTimeout(hideUndo, 5000);
}
function hideUndo(){
  const t = $("toast"); clearTimeout(undoTimer);
  t.classList.remove("in"); t.classList.add("out");
  setTimeout(() => { if (t.classList.contains("out")) t.hidden = true; }, 250);
}

let view = "matches", cats = new Set();
let place = null;   // {key, label}: show only jobs from one location
const placeKey = r => r.ll ? r.ll.join(",") : (r.loc || "").trim().toLowerCase();
function setPlace(key, label){
  place = key ? {key, label} : null;
  $("placechip").hidden = !place; $("placename").textContent = place ? label : "";
  window.scrollTo({top: 0, behavior: "smooth"});
  draw();
}
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function base(){
  const min = +$("minscore").value;
  // every open job found, unfiltered; saved/applied also ignore the score filter
  if (view === "all" || view === "interested" || view === "applied" || view === "rejected") return DATA.rows;
  return DATA.rows.filter(r => {
    if (!r.pre) return $("showfiltered").checked;
    if (r.score == null) return true;          // unscored (no API key yet) — show
    return r.score >= min && r.nl !== false;
  });
}
const VIEWS = {
  matches: {label:"Matches", f: r => true},
  new: {label:"New this week", f: r => daysSince(r.first_seen) <= 7},
  closing: {label:"Closing in 14 days", f: r => { const d = daysTo(r.deadline); return d !== null && d >= 0 && d <= 14; }},
  interested: {label:"Interested", f: r => marks[r.key] === "interested"},
  applied: {label:"Applied", f: r => marks[r.key] === "interested" && applied[r.key]},
  rejected: {label:"Rejected", f: r => marks[r.key] === "hidden"},
  all: {label:"All found (unfiltered)", f: r => true},
};

function renderStats(){
  const cur = view;
  $("stats").innerHTML = Object.entries(VIEWS).map(([k,v]) => {
    view = k;   // base() depends on the view
    const n = base().filter(r => k === "rejected" || marks[r.key] !== "hidden").filter(v.f).length;
    return `<div class="stat ${k===cur?"on":""}" data-v="${k}"><b>${n}</b><span>${v.label}</span></div>`;
  }).join("");
  view = cur;
  $("stats").querySelectorAll(".stat").forEach(el => el.onclick = () => { view = el.dataset.v; draw(); });
}

function card(r){
  const sc = r.score;
  const col = sc == null ? "" : sc >= 7 ? "var(--s-hi)" : sc >= 5 ? "var(--s-mid)" : "var(--s-lo)";
  const dl = daysTo(r.deadline);
  const tags = [];
  if (daysSince(r.first_seen) <= 2) tags.push(`<span class="tag new">NEW</span>`);
  if (dl !== null && dl >= 0) tags.push(`<span class="tag ${dl<=7?"urgent":"dl"}"><span class="mi">schedule</span>Deadline ${r.deadline} · ${dl===0?"today":dl+" day"+(dl===1?"":"s")}</span>`);
  if (r.cat) tags.push(`<a class="tag cattag" href="#" data-c="${esc(r.cat)}" title="Show only ${esc(CATS[r.cat]||r.cat)} jobs">${CATS[r.cat]||r.cat}</a>`);
  if (DUTCH[r.dutch]) tags.push(`<span class="tag">${DUTCH[r.dutch]}</span>`);
  tags.push(`<span class="tag"><span class="mi">link</span>via ${esc(r.source)}${r.also.map(a=>`, <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.source)}</a>`).join("")}</span>`);
  if (!r.pre) tags.push(`<span class="tag">filtered: ${esc(r.pre_reason)}</span>`);
  const m = marks[r.key];
  return `<article class="card ${m==="hidden"&&view!=="rejected"?"dim":""} ${m==="interested"?"liked":""}" data-k="${esc(r.key)}" data-url="${esc(r.url)}">
    <div class="score ${sc==null?"na":""}" style="${col?`background:${col}`:""}" title="Fit score (0-10)">${sc==null?"–":sc}</div>
    <div>
      <a class="title" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>
      <div class="meta"><span><span class="mi">apartment</span>${esc(r.org)}</span>${r.loc?`<a class="placelink" href="#" data-place="${esc(placeKey(r))}" data-label="${esc(r.loc)}" title="Show only jobs in ${esc(r.loc)}"><span class="mi">location_on</span>${esc(r.loc)}</a>`:""}<span><span class="mi">visibility</span>first seen ${esc(r.first_seen)}</span></div>
      <div class="tags">${tags.join("")}</div>
      ${r.summary?`<p class="summary">${esc(r.summary)}</p>`:""}
      ${r.why?`<p class="why">${esc(r.why)}</p>`:""}
      ${r.blockers?.length?`<p class="blockers"><span class="mi">warning</span> ${r.blockers.map(esc).join(" · ")}</p>`:""}
      <div class="actions">
        <button class="vote yes ${m==="interested"?"on":""}" data-k="${esc(r.key)}" data-m="interested" title="Interested (or swipe right)" aria-label="Interested"><span class="fill"></span><span class="mi">check</span></button>
        <button class="vote no ${m==="hidden"?"on":""}" data-k="${esc(r.key)}" data-m="hidden" title="Not interested (or swipe left)" aria-label="Not interested"><span class="fill"></span><span class="mi">close</span></button>
        ${m==="interested" ? `<label class="applybox ${applied[r.key]?"on":""}"><input type="checkbox" data-k="${esc(r.key)}" ${applied[r.key]?"checked":""}><span class="mi">${applied[r.key]?"task_alt":"radio_button_unchecked"}</span>Applied</label>` : ""}
      </div>
    </div></article>`;
}

function draw(){
  renderStats();
  const q = $("q").value.trim().toLowerCase();
  let rows = base().filter(VIEWS[view].f)
    .filter(r => view === "rejected" || $("showhidden").checked || marks[r.key] !== "hidden")
    .filter(r => !cats.size || cats.has(r.cat))
    .filter(r => !place || placeKey(r) === place.key)
    .filter(r => !q || [r.title,r.org,r.summary,r.loc].join(" ").toLowerCase().includes(q));
  const s = view === "closing" ? "deadline" : $("sort").value;
  const dlKey = r => { const d = daysTo(r.deadline); return d === null || d < 0 ? 9999 : d; };
  rows.sort((a,b) => s === "deadline" ? dlKey(a)-dlKey(b) || (b.score??-1)-(a.score??-1)
    : s === "new" ? (b.first_seen||"").localeCompare(a.first_seen||"") || (b.score??-1)-(a.score??-1)
    : (b.score??-1)-(a.score??-1) || dlKey(a)-dlKey(b));
  $("count").textContent = `${rows.length} job${rows.length===1?"":"s"}` +
    (view === "all" ? " — everything the scan found, including jobs the filter would hide (reason shown on each)" : "");
  $("map").hidden = !mapMode; $("list").hidden = mapMode; $("nomap").hidden = !mapMode;
  if (mapMode) return drawMap(rows);
  $("list").innerHTML = rows.length ? rows.map(card).join("") : `<div class="empty">Nothing here right now.</div>`;
  $("list").querySelectorAll(".cattag").forEach(a => a.onclick = e => { e.preventDefault(); setCat(a.dataset.c); });
  $("list").querySelectorAll(".placelink").forEach(a => a.onclick = e => { e.preventDefault(); setPlace(a.dataset.place, a.dataset.label); });
  $("list").querySelectorAll(".vote").forEach(b => b.onclick = () => setMark(b.dataset.k, b.dataset.m));
  $("list").querySelectorAll(".applybox input").forEach(cb => cb.onchange = () => {
    if (cb.checked) applied[cb.dataset.k] = true; else delete applied[cb.dataset.k];
    saveMarks(cb.dataset.k); draw();
  });
  $("list").querySelectorAll(".card").forEach(c => {
    wireSwipe(c);
    c.addEventListener("click", e => {          // whole card opens the ad (except its own controls)
      if (e.target.closest("a,button,input,label,select") || c.dataset.dragged) return;
      if (String(getSelection()).length) return;   // don't hijack text selection
      window.open(c.dataset.url, "_blank", "noopener");
    });
  });
}

// Swipe a card: right = interested, left = not interested
function wireSwipe(el){
  const k = el.dataset.k;
  let x0 = 0, y0 = 0, dx = 0, tracking = false, dragging = false;
  let badge = null;
  const paint = (p, dir, ms = 0) => {   // everything scales continuously with drag progress p (0..1)
    const tr = ms ? `all ${ms}ms ease` : "none";
    if (!badge) { badge = document.createElement("div"); el.appendChild(badge); }
    badge.className = `swipebadge ${dir}`;
    badge.innerHTML = `<span class="mi">${dir === "yes" ? "check" : "close"}</span>`;
    badge.style.transition = tr;
    badge.style.opacity = p;
    badge.style.transform = `scale(${.3 + .7 * p}) rotate(${(1 - p) * (dir === "yes" ? -30 : 30)}deg)`;
    el.dataset.dir = dir; el.style.setProperty("--p", p);
    el.querySelectorAll(".vote").forEach(b => {
      const mine = b.classList.contains(dir), q = mine ? p : 0, f = b.querySelector(".fill"), i = b.querySelector(".mi");
      if (b.classList.contains("on") && !mine) return;
      b.style.transition = tr; f.style.transition = tr; i.style.transition = tr;
      f.style.opacity = b.classList.contains("on") ? 1 : q;
      b.style.transform = `scale(${1 + .2 * q})`;
      i.style.color = (q > .45 || b.classList.contains("on")) ? "#fff" : "";
    });
  };
  const reset = () => { el.style.transition = "transform .25s ease"; el.style.transform = "";
                        paint(0, el.dataset.dir || "yes", 250); setTimeout(() => { el.style.transition = ""; }, 260); };
  el.addEventListener("pointerdown", e => {
    if (e.button !== 0 || e.target.closest("a,button,input,label,select")) return;
    x0 = e.clientX; y0 = e.clientY; dx = 0; tracking = true; dragging = false;
  });
  el.addEventListener("pointermove", e => {
    if (!tracking) return;
    const mx = e.clientX - x0, my = e.clientY - y0;
    if (!dragging) {
      if (Math.abs(mx) < 10 && Math.abs(my) < 10) return;
      if (Math.abs(my) > Math.abs(mx)) { tracking = false; return; }   // vertical: let the page scroll
      dragging = true; try { el.setPointerCapture(e.pointerId); } catch (_) {} el.classList.add("dragging");
    }
    dx = mx;
    el.style.transform = `translateX(${dx}px) rotate(${dx / 45}deg)`;
    paint(Math.min(1, Math.abs(dx) / 110), dx >= 0 ? "yes" : "no");
  });
  const end = () => {
    if (!tracking) return;
    tracking = false;
    if (!dragging) return;
    el.classList.remove("dragging");
    el.dataset.dragged = "1"; setTimeout(() => { delete el.dataset.dragged; }, 350);
    if (dx > 90) {                       // interested: button lights up, card springs back
      paint(1, "yes", 120);
      el.style.transition = "transform .3s cubic-bezier(.2,1.4,.4,1)"; el.style.transform = "";
      setTimeout(() => { el.querySelector(".vote.yes")?.classList.add("on"); paint(0, "yes", 300); }, 260);
      setTimeout(() => setMark(k, "interested", true), 600);
    }
    else if (dx < -90) {                 // not interested: button lights up, card flies away
      paint(1, "no", 100);
      el.querySelector(".vote.no")?.classList.add("on");
      el.style.transition = "transform .28s ease, opacity .28s ease";
      el.style.transform = "translateX(-120%) rotate(-10deg)"; el.style.opacity = "0";
      setTimeout(() => setMark(k, "hidden", true), 260);
    } else reset();
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", () => { tracking = false; el.classList.remove("dragging"); reset(); });
}

let mapMode = false, map = null, layer = null;
const scoreCol = s => s == null ? "#a79cab" : s >= 7 ? "#7b2d8e" : s >= 5 ? "#c2378a" : "#a79cab";
function drawMap(rows){
  if (!window.L) { $("nomap").hidden = false; $("nomap").textContent = "The map library couldn't load."; return; }
  if (!map) {
    map = L.map("map").setView([52.2, 5.3], 7);
    // one free OpenStreetMap layer; in dark mode CSS inverts it into a dark map (no API key needed)
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);
    wirePopups();
  }
  if (layer) layer.remove();
  layer = L.layerGroup().addTo(map);
  const places = new Map();
  let missing = 0;
  rows.forEach(r => {
    if (!r.ll) { missing++; return; }
    const k = r.ll.join(",");
    if (!places.has(k)) places.set(k, []);
    places.get(k).push(r);
  });
  places.forEach(list => {
    list.sort((a,b) => (b.score??-1)-(a.score??-1));
    const best = list[0].score;
    const n = list.length;
    const icon = L.divIcon({className: "", iconSize: null, html:
      `<div style="background:${scoreCol(best)};color:#fff;border:2px solid #fff;border-radius:999px;
        min-width:${n>9?30:24}px;height:24px;line-height:20px;text-align:center;font:600 12px sans-serif;
        box-shadow:0 1px 4px rgba(0,0,0,.35);transform:translate(-50%,-50%);padding:0 4px">${n}</div>`});
    const placeLabel = list[0].loc || "";
    const html = `<div class="pop"><h4>${esc(placeLabel)} — ${n} job${n===1?"":"s"}</h4>` +
      `<button class="onlyhere" data-place="${esc(placeKey(list[0]))}" data-label="${esc(placeLabel)}"><span class="mi">filter_alt</span>Show only these jobs</button>` + list.map(r => {
      const dl = daysTo(r.deadline);
      return `<div><b style="background:${scoreCol(r.score)}">${r.score ?? "–"}</b>` +
        `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` +
        `<br><span style="color:#6f6474">${esc(r.org)}${dl!==null&&dl>=0?` · deadline in ${dl} d`:""}</span></div>`;
    }).join("") + `</div>`;
    L.marker(list[0].ll, {icon}).bindPopup(html, {maxWidth: 280, autoPanPaddingTopLeft: [50, 20]}).addTo(layer);
  });
  setTimeout(() => {
    map.invalidateSize();
    if (!map._framed) { map.fitBounds([[50.75, 3.35], [53.55, 7.2]]); map._framed = true; }   // the Netherlands
  }, 0);
  $("nomap").textContent = missing ? `${missing} job${missing===1?"":"s"} without a known location aren't shown on the map.` : "";
}
$("placechip").onclick = () => setPlace(null);
// show the small logo in the sticky bar once the page header has scrolled away
new IntersectionObserver(([e]) => $("controls").classList.toggle("stuck", !e.isIntersecting))
  .observe(document.querySelector("header"));
$("minilogo").onclick = e => { e.preventDefault(); window.scrollTo({top: 0, behavior: "smooth"}); };
function setCat(c, scroll = true){   // show only this job type ("" = all types)
  cats = c ? new Set([c]) : new Set();
  $("type").value = c || "";
  $("typechip").hidden = !c; $("typename").textContent = c ? CATS[c] : "";
  if (scroll) window.scrollTo({top: 0, behavior: "smooth"});
  draw();
}
$("typechip").onclick = () => setCat("", false);
$("btnFilters").onclick = () => {
  const open = $("filters").classList.toggle("open");
  $("btnFilters").classList.toggle("on", open); $("btnFilters").setAttribute("aria-expanded", open);
};
function updateFilterDot(){
  $("fdot").hidden = $("minscore").value === "5" && $("sort").value === "score" &&
    !$("showhidden").checked && !$("showfiltered").checked;
}
function wirePopups(){
  map.on("popupopen", e => {
    const b = e.popup.getElement().querySelector(".onlyhere");
    if (b) b.onclick = () => {
      map.closePopup();
      mapMode = false; $("btnList").classList.add("on"); $("btnMap").classList.remove("on");
      setPlace(b.dataset.place, b.dataset.label);
    };
  });
}
$("btnList").onclick = () => { mapMode = false; $("btnList").classList.add("on"); $("btnMap").classList.remove("on"); draw(); };
$("btnMap").onclick = () => { mapMode = true; $("btnMap").classList.add("on"); $("btnList").classList.remove("on"); draw(); };

Sync.init();
$("unscored").hidden = !DATA.rows.some(r => r.pre && r.score == null);
$("gen").textContent = "updated " + new Date(DATA.generated).toLocaleString();
$("type").insertAdjacentHTML("beforeend", Object.entries(CATS).map(([k,v]) => `<option value="${k}">${v}</option>`).join(""));
$("type").addEventListener("input", () => setCat($("type").value, false));
["q","minscore","sort","showhidden","showfiltered"].forEach(id => $(id).addEventListener("input", () => { updateFilterDot(); draw(); }));
$("srcs").innerHTML = Object.entries(DATA.sources).map(([k,v]) =>
  `<tr><td>${esc(k)}</td><td>${v.ok?`${v.count} jobs, ${v.new} new`:`<span class="bad">failed: ${esc(v.error)}</span>`}</td></tr>`).join("");
draw();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
</script>
</body>
</html>
"""
