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


def dedupe_key(title: str, org: str) -> str | None:
    """Key for spotting the same ad on several sites. Long titles are distinctive on their
    own (orgs are often spelled differently across boards); short ones also need the org."""
    nt = _norm(title)
    if len(nt) >= 25:
        return nt
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
        dk = dedupe_key(row["title"], row["org"])
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
<title>NL Biology Job Scout</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧬</text></svg>">
<style>
:root{
  --bg:#f6f5f1; --panel:#fff; --ink:#1d2320; --muted:#667069; --line:#e3e1da;
  --accent:#1f6f5c; --accent-soft:#e3f0eb; --warn:#b4541a; --warn-soft:#fbeadf;
  --danger:#b3261e; --chip:#efede7;
  --s-hi:#1f6f5c; --s-mid:#7a8f2a; --s-lo:#a39e93;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#121513; --panel:#1b1f1c; --ink:#e6e9e6; --muted:#98a29b; --line:#2c322e;
    --accent:#5fbf9f; --accent-soft:#1f3029; --warn:#e89a5f; --warn-soft:#3a2a1e; --danger:#ef7a70;
    --chip:#262b27; --s-hi:#5fbf9f; --s-mid:#b3c45a; --s-lo:#6f756f;}
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
</style>
</head>
<body>
<header>
  <h1>🧬 NL Biology Job Scout</h1>
  <div class="sub">Genetics · conservation · aquaculture jobs in the Netherlands — updated daily. <span id="gen"></span></div>
  <div class="stats" id="stats"></div>
</header>
<main>
  <div class="controls">
    <input type="search" id="q" placeholder="Search title, organization, summary…">
    <select id="minscore" title="Minimum fit score">
      <option value="7">Score ≥ 7</option><option value="5" selected>Score ≥ 5</option>
      <option value="3">Score ≥ 3</option><option value="0">All scored</option>
    </select>
    <select id="sort"><option value="score">Sort: best fit</option><option value="deadline">Sort: deadline</option><option value="new">Sort: newest</option></select>
    <div class="chips" id="cats"></div>
    <label class="tog"><input type="checkbox" id="showhidden"> show dismissed</label>
    <label class="tog"><input type="checkbox" id="showfiltered"> show keyword-filtered</label>
  </div>
  <div class="notice" id="unscored" hidden>Some jobs have no score yet. They'll be scored on the next daily run.</div>
  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
    <div class="count" id="count"></div>
    <div class="seg"><button id="btnList" class="on">☰ List</button><button id="btnMap">🗺 Map</button></div>
  </div>
  <div id="map" hidden></div>
  <div class="nomap" id="nomap" hidden></div>
  <div id="list"></div>
  <details class="srcs"><summary>Sources in the last run</summary><table id="srcs"></table></details>
</main>
<script>
const DATA = __DATA__;
const CATS = {phd:"PhD", technician_research:"Technician / research", conservation_zoo_ngo:"Conservation / zoo / NGO", industry:"Industry", other:"Other"};
const DUTCH = {basic:"Dutch: basic", fluent:"Dutch: fluent required"};
const today = new Date(); today.setHours(0,0,0,0);
const daysTo = d => d ? Math.round((new Date(d+"T00:00:00") - today)/864e5) : null;
const daysSince = d => d ? Math.round((today - new Date(d+"T00:00:00"))/864e5) : 999;

let marks = {};
try { marks = JSON.parse(localStorage.getItem("marks") || "{}"); } catch(e) {}
const saveMarks = () => { try { localStorage.setItem("marks", JSON.stringify(marks)); } catch(e) {} };

let view = "matches", cats = new Set();
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function base(){
  const min = +$("minscore").value;
  if (view === "all") return DATA.rows;        // every open job found, unfiltered
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
  saved: {label:"Saved", f: r => marks[r.key] === "saved"},
  all: {label:"All found (unfiltered)", f: r => true},
};

function renderStats(){
  const cur = view;
  $("stats").innerHTML = Object.entries(VIEWS).map(([k,v]) => {
    view = k;   // base() depends on the view
    const n = base().filter(r => marks[r.key] !== "hidden").filter(v.f).length;
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
  if (dl !== null && dl >= 0) tags.push(`<span class="tag ${dl<=7?"urgent":"dl"}">Deadline ${r.deadline} · ${dl===0?"today":dl+" day"+(dl===1?"":"s")}</span>`);
  if (r.cat) tags.push(`<span class="tag">${CATS[r.cat]||r.cat}</span>`);
  if (DUTCH[r.dutch]) tags.push(`<span class="tag">${DUTCH[r.dutch]}</span>`);
  tags.push(`<span class="tag">via ${esc(r.source)}${r.also.map(a=>`, <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.source)}</a>`).join("")}</span>`);
  if (!r.pre) tags.push(`<span class="tag">filtered: ${esc(r.pre_reason)}</span>`);
  const m = marks[r.key];
  return `<article class="card ${m==="hidden"?"dim":""}">
    <div class="score ${sc==null?"na":""}" style="${col?`background:${col}`:""}" title="Fit score (0-10)">${sc==null?"–":sc}</div>
    <div>
      <a class="title" href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>
      <div class="meta"><span>${esc(r.org)}</span>${r.loc?`<span>📍 ${esc(r.loc)}</span>`:""}<span>first seen ${esc(r.first_seen)}</span></div>
      <div class="tags">${tags.join("")}</div>
      ${r.summary?`<p class="summary">${esc(r.summary)}</p>`:""}
      ${r.why?`<p class="why">${esc(r.why)}</p>`:""}
      ${r.blockers?.length?`<p class="blockers">⚠ ${r.blockers.map(esc).join(" · ")}</p>`:""}
      <div class="actions">
        <button data-k="${esc(r.key)}" data-m="saved" class="${m==="saved"?"on":""}">★ Save</button>
        <button data-k="${esc(r.key)}" data-m="applied" class="${m==="applied"?"on":""}">✓ Applied</button>
        <button data-k="${esc(r.key)}" data-m="hidden" class="${m==="hidden"?"on":""}">✕ Not interested</button>
      </div>
    </div></article>`;
}

function draw(){
  renderStats();
  const q = $("q").value.trim().toLowerCase();
  let rows = base().filter(VIEWS[view].f)
    .filter(r => $("showhidden").checked || marks[r.key] !== "hidden")
    .filter(r => !cats.size || cats.has(r.cat))
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
  $("list").querySelectorAll(".actions button").forEach(b => b.onclick = () => {
    const k = b.dataset.k; marks[k] = marks[k] === b.dataset.m ? undefined : b.dataset.m;
    if (!marks[k]) delete marks[k]; saveMarks(); draw();
  });
}

let mapMode = false, map = null, layer = null;
const scoreCol = s => s == null ? "#a39e93" : s >= 7 ? "#1f6f5c" : s >= 5 ? "#7a8f2a" : "#a39e93";
function drawMap(rows){
  if (!window.L) { $("nomap").hidden = false; $("nomap").textContent = "The map library couldn't load."; return; }
  if (!map) {
    map = L.map("map").setView([52.2, 5.3], 7);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {maxZoom: 18, attribution: "© OpenStreetMap contributors"}).addTo(map);
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
    const place = list[0].loc || "";
    const html = `<div class="pop"><h4>${esc(place)} — ${n} job${n===1?"":"s"}</h4>` + list.map(r => {
      const dl = daysTo(r.deadline);
      return `<div><b style="background:${scoreCol(r.score)}">${r.score ?? "–"}</b>` +
        `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` +
        `<br><span style="color:#667069">${esc(r.org)}${dl!==null&&dl>=0?` · deadline in ${dl} d`:""}</span></div>`;
    }).join("") + `</div>`;
    L.marker(list[0].ll, {icon}).bindPopup(html, {maxWidth: 320}).addTo(layer);
  });
  setTimeout(() => map.invalidateSize(), 0);
  $("nomap").textContent = missing ? `${missing} job${missing===1?"":"s"} without a known location aren't shown on the map.` : "";
}
$("btnList").onclick = () => { mapMode = false; $("btnList").classList.add("on"); $("btnMap").classList.remove("on"); draw(); };
$("btnMap").onclick = () => { mapMode = true; $("btnMap").classList.add("on"); $("btnList").classList.remove("on"); draw(); };

$("unscored").hidden = !DATA.rows.some(r => r.pre && r.score == null);
$("gen").textContent ="Last update: " + new Date(DATA.generated).toLocaleString();
$("cats").innerHTML = Object.entries(CATS).map(([k,v]) => `<span class="chip" data-c="${k}">${v}</span>`).join("");
$("cats").querySelectorAll(".chip").forEach(c => c.onclick = () => {
  cats.has(c.dataset.c) ? cats.delete(c.dataset.c) : cats.add(c.dataset.c); c.classList.toggle("on"); draw(); });
["q","minscore","sort","showhidden","showfiltered"].forEach(id => $(id).addEventListener("input", draw));
$("srcs").innerHTML = Object.entries(DATA.sources).map(([k,v]) =>
  `<tr><td>${esc(k)}</td><td>${v.ok?`${v.count} jobs, ${v.new} new`:`<span class="bad">failed: ${esc(v.error)}</span>`}</td></tr>`).join("");
draw();
</script>
</body>
</html>
"""
