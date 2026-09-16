# BioJobs 🧬

A free daily scanner for biology jobs in the Netherlands (genetics, population genetics, conservation,
aquaculture). It collects vacancies from ~25 job sites and employers, drops unsuitable ones, scores the
rest with keyword rules, and publishes a dashboard page with new matches and upcoming deadlines.
No paid APIs are needed.

```
jobscan/sources/*.py   → fetch open vacancies (one module per site)
jobscan/prefilter.py   → drop postdoc/professor/vet/internship/volunteer roles and non-biology ads
jobscan/scorer.py      → fit score 0-10 from weighted keywords, job type, requirements, Dutch level
data/jobs.json         → history (first seen, still open?)
docs/index.html        → the dashboard;  data/digest.md → daily digest (email / GitHub issue)
```

## Sources
| Kind | Sources |
|---|---|
| Academic | AcademicTransfer, EURAXESS, Netherlands Cancer Institute (AVL), Nature Careers, Utrecht University, UvA, Leiden, LUMC, UMC Utrecht, WUR, KNAW institutes (NIOO, Westerdijk, Hubrecht…) |
| Wageningen area | WUR, KeyGene, Solynta, NIZO, Noldus, Hendrix Genetics |
| Nature / zoos / NGOs | Greenjobs, Sustainable Jobs, Fondsen, Groene Ruimte, Naturalis, NIOZ, EAZA, Staatsbosbeheer, ARTIS, Blijdorp, Burgers' Zoo, Apenheul, GaiaZOO, WWF-NL, Vogelbescherming, Sovon, RAVON, Vlinderstichting, Zodion, IUCN NL… |
| Industry | Nutreco/Skretting/Trouw, CRV, Topigs Norsvin, Koppert, Enza, Bejo, Syngenta, Dümmen Orange, BaseClear, GenomeScan, Cobb, Eurofins |
| Government / general | Werken voor Nederland, werk.nl (UWV), werkzoeken.nl, optional Adzuna / Jooble |

Indeed, LinkedIn, Nationale Vacaturebank and Monsterboard block automated access, so they aren't
scanned. Their NL ads often also appear on werk.nl / werkzoeken.nl or the employer's own site.

## Setup (one time, ~10 minutes)
1. **Create a GitHub repository** and push this folder to it:
   ```bash
   git init && git add . && git commit -m "BioJobs"
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
   GitHub Pages is free for public repos. The page is marked `noindex`.
2. **Turn on the page**: *Settings → Pages → Build from branch → `main` / `/docs`*.
   It will be at `https://<you>.github.io/<repo>/`.
3. **Run it the first time**: *Actions → Daily job scan → Run workflow*. The first run is slow
   (it reads every ad), up to ~1-2 hours. After that it runs every morning around 07:15 Amsterdam time and takes a few minutes.

### Optional notifications
- **GitHub issue per day** (easiest): *Settings → Secrets and variables → Actions → Variables* →
  add `DIGEST_ISSUES` = `true`. Anyone who *Watches* the repo gets it by email from GitHub.
- **Email**: add secrets `SMTP_HOST` (e.g. `smtp.gmail.com`), `SMTP_USER`, `SMTP_PASSWORD`
  (for Gmail, an [app password](https://myaccount.google.com/apppasswords)) and `EMAIL_TO`.

The digest lists new matches scoring ≥ 6 and reminds about them 7, 3 and 1 day(s) before the deadline.

### Optional extra sources (free keys)
- Adzuna: https://developer.adzuna.com → secrets `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`
- Jooble: https://jooble.org/api/about → secret `JOOBLE_API_KEY`

## Tuning
- **What ranks high** → the `TOPICS`, `OFF_TOPICS` and `TYPE_ADJ` lists at the top of
  [`jobscan/scorer.py`](jobscan/scorer.py). All open jobs are re-scored on every run, so edits apply right away.
- **Translation** → Dutch ads are translated to English during the scan with the open-source OPUS-MT model — title, summary and the full text (`jobscan/translate.py`, cached in `data/translations.json` and `data/fulltext_en.json`). The EN/NL button switches the whole page back to the original Dutch. Whole ads are translated newest-and-best-first with a time budget (`TRANSLATE_BUDGET_S`, default 25 min), so a backlog is worked through over several runs instead of overrunning the daily job.
- **What gets dropped entirely** → [`jobscan/prefilter.py`](jobscan/prefilter.py).
- On the page, tap ✓ / ✕ (or swipe a card right / left) to mark Interested / Not interested; Interested jobs get an Applied checkbox. Marks are stored in the browser; tap the cloud button (top right) to sync them across devices through a private GitHub Gist (needs a fine-grained token with only the Gists permission, entered on one device; other devices connect with the link it gives).

## Running locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m jobscan.main                 # everything
.venv/bin/python -m jobscan.main --only wur uu   # some sources
open docs/index.html
```

## Adding a source
Create `jobscan/sources/<name>.py` with `NAME` and `fetch() -> list[Job]` (see `sources/base.py`).
Add `enrich(job)` if the detail page is needed for the description or deadline. It is only called for
new jobs. Set `DOMAIN_SPECIFIC = True` when every vacancy is in-domain (zoos, nature NGOs), so the
keyword filter doesn't drop them. Sources are discovered automatically. A failing source is shown on
the page and doesn't break the run.
