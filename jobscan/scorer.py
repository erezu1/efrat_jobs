"""Rule-based fit scoring (free, no API). Edit the weight lists below to tune what ranks high.

Each job gets: fit_score 0-10, category, summary, why, blockers, dutch_required, deadline,
in_netherlands. Scoring is cheap, so every active job is re-scored on every run and rule
changes apply to everything immediately.
"""
from __future__ import annotations

import re

from .sources.base import Job
from .sources.nature_employers import find_deadline

# ---------------------------------------------------------------------------------------
# TOPICS: (regex, points if in title, points if only in description). Each pattern counts once.
# ---------------------------------------------------------------------------------------
TOPICS = [
    # Top interests
    (r"population\s+genetic|populatiegenetica|conservation\s+genetic|landscape\s+genetic", 5, 3),
    (r"endangered|threatened\s+species|bedreigde\s+(dier)?soort|red\s+list|rode\s+lijst|IUCN", 4, 2),
    (r"conservation|natuurbehoud|soortbescherming|species\s+protection|rewilding", 3, 1.5),
    (r"biodiversit", 3, 1.5),
    (r"wildlife|wilde\s+dieren|\bzoo\b|dierentuin|EAZA|breeding\s+programme|fokprogramma|\bEEP\b", 3, 1.5),
    (r"\beDNA\b|environmental\s+DNA", 4, 2),
    (r"\bfish|\bvissen\b|vissoort|visserij|visstand|fisheries|ichthy|aquacult|aquacultuur|salmon|\bzalm", 4, 2),
    # Strong
    (r"(?<![a-z])genetic|(?<![a-z])genetica|(?<![a-z])genetisch", 3, 1.5),   # not "optogenetic"
    (r"genomic|genomics|\bgenoom|\bgenomes?\b", 3, 1.5),   # not Dutch "genomen" (= taken)
    (r"animal\s+breeding|fokkerij|breeding\s+value|quantitative\s+genetic", 3, 1.5),
    (r"evolution|evolutie|phylogen|fylogen", 2.5, 1),
    (r"ecolog|ecoloog", 2.5, 1),
    (r"\bnatuur|\bnature\b|\bgroen\s+beheer|natuurbeheer|boswachter|ranger", 1.5, 0.5),
    (r"zoolog|animal\s+science|dierwetenschap|animal\s+ecology|animal\s+behaviou?r|diergedrag", 2.5, 1),
    (r"(?<!Koninklijke\s)\bmarine\b|mariene|\bsea\b|oceanogr|\bcoral|koraal|North\s+Sea|Noordzee|zeehond|\bseals?\b", 2, 1),
    (r"\bbirds?\b|\bvogels?\b|ornitholog|mammal|zoogdier|amphibi|amfibie|reptiel|reptile|\binsect|vlinder", 2, 1),
    (r"\bspecies\b|diersoort|vissoort|soortbescherming|taxonom|monitoring", 1.5, 0.5),
    # Molecular / cell biology research (e.g. research assistant in a biomedical lab) — relevant too
    (r"molecular\s+biolog|moleculaire\s+biolog|\bmolecul|\bmoleculair|cell\s+biolog|celbiolog|oncogenomic", 3, 1.5),
    (r"\bDNA\b|\bRNA\b|\bPCR\b|qPCR|sequencing|sequencen|CRISPR|genetic\s+screen|cloning|kloneren|"
     r"cell\s+culture|celkweek|western\s+blot|flow\s+cytometr|microscop|genome\s+(in)?stabilit|DNA\s+repair", 2, 1.5),
    (r"bioinformatic|bio-informatica", 2, 1),
    (r"laborator|\blab\b", 1.5, 0.5),
    (r"\bbiolog|life\s+science|levenswetenschap|biomedic|biomedisch", 1.5, 0.5),
]

DESC_CAP = 4.5   # max points from topic words that appear only in the description

# Off-profile topics: (regex, penalty if in title, penalty if only in description)
OFF_TOPICS = [
    # patient care / clinical routine (biomedical *research* topics like cancer or neuro are fine)
    (r"verpleeg|\bnurse|zorgmedewerker|doktersassistent|poli(kliniek)?assistent|patiëntenzorg|patient\s+care|"
     r"\bklinisch\s+(chemisch|fysicus)|radiotherap|anesthes|operatie|\bOK\b|\bAIOS\b|\bANIOS\b|arts-assistent", 4, 0),
    (r"patient|pati[eë]nt|hospital|ziekenhuis|clinical\s+trial|klinisch", 1, 0),
    (r"psychiatr|psycholog|linguist|cognitive|cognitie", 3, 0.5),
    (r"physics|natuurkunde|quantum|photonic|optic|semiconductor|electrocataly|chemistry|chemie", 3, 0.5),
    (r"software|developer|ICT|\bIT\b|data\s+engineer|cyber|machine\s+learning|\bAI\b", 2, 0),
    (r"econom|financ|controller|accountant|marketing|law\b|juridisch|jurist|linguist|taalkunde|history", 3, 0),
    (r"\bHR\b|recruit|communicat|secretar|office|administrat", 2, 0),
    (r"beleidsmedewerker|beleidsadviseur|policy\s+officer|\badviseur\b|consultant", 1, 0),
    (r"production\s+worker|productiemedewerker|\boperator\b|chauffeur|driver|\bsales\b|verkoop|"
     r"technische\s+dienst|facilit|horeca|catering|schoonmaak|kassa|receptie|magazijn|logistiek", 3, 0),
    (r"dierverzorg|animal\s+care(taker)?|zookeeper|oppasser", 3, 0),   # she wants to move on from animal care
    (r"koninklijke\s+marine|defensie|\bnavy\b", 4, 0),
    (r"energie|\benergy\b|riolering|vergunning|elektrotechn|werktuigbouw|bouwkund|civiel|civil\s+engineer", 2, 0),
    (r"\bpharmacist|apotheek|farmaceutisch\s+(consulent|assistent)", 2, 0),
    (r"crop|gewas|plant\s+breeding|plantenveredeling|soil|bodem|\bplant", 1, 0),
]

# Job-type adjustments on the title
TYPE_ADJ = [
    (r"\bph\.?d\b|promovend|doctoral\s+candidate", +1, "PhD position"),
    (r"research\s+assistant|onderzoeksassistent|research\s+technician|lab(oratory)?\s+technician|"
     r"laborant|analist|\banalyst\b|technicus|technician", +2, "technician / research role"),
    (r"researcher|onderzoeker|scientist|wetenschapper", +1, "research role"),
    (r"\bsenior\b|\bmanager\b|director|directeur|\bhead\b|\bhoofd\b|teamleider|team\s+lead|"
     r"\blead\b|principal", -2, "senior / management level"),
]

NATURE_SOURCES = {"nature_employers", "greenjobs", "sustainablejobs", "fondsen", "groeneruimte"}
INDUSTRY_SOURCES = {"industry", "wageningen_companies", "eurofins"}

# Requirement detection in the description
PHD_REQUIRED = re.compile(
    r"(?i)(completed|hold|have|with)\s+(a\s+)?(PhD|doctorate)(?!\s*(student|candidate|position|project|researcher|program|traject))|"
    r"PhD\s+(degree\s+)?(is\s+)?required|"
    r"gepromoveerd|afgeronde\s+promotie|doctoral\s+degree\s+in")
DVM_REQUIRED = re.compile(r"(?i)\bDVM\b|veterinary\s+degree|diergeneeskunde|dierenarts\b|\bMD\b|medical\s+degree|basisarts|BIG-regist")
DUTCH_FLUENT = re.compile(
    r"(?i)(fluent|native|excellent|very\s+good|full\s+professional)\s+(command\s+of\s+|proficiency\s+in\s+|in\s+)?(the\s+)?Dutch|"
    r"Dutch\s+(at\s+)?(C1|C2|native|fluent)|uitstekende?\s+(beheersing|kennis)\s+van\s+de\s+Nederlandse|"
    r"Nederlands\s+(op\s+)?(C1|C2|moedertaal)|(zeer\s+)?goede\s+beheersing\s+van\s+de\s+Nederlandse\s+taal|"
    r"Nederlands\s+(in\s+)?woord\s+en\s+geschrift")
DUTCH_ANY = re.compile(r"(?i)\bDutch\b|Nederlandse\s+taal|\bNederlands\b")
YEARS_EXP = re.compile(
    r"(?i)(?:at\s+least|minimum\s+(?:of\s+)?|minimaal|ten\s+minste|minstens)?\s*(\d{1,2})\+?\s*"
    r"(?:or\s+more\s+)?(?:years?|jaar)\s+(?:of\s+)?(?:relevant\w*\s+|professional\s+|werk)?(?:experience|ervaring|werkervaring)")
FOREIGN_IN_TITLE = re.compile(r"\((?:[^)]*,\s*)?(?!NL\b)([A-Z]{2}|UK|Spain|France|Germany|Italy|Belgium|Cyprus|Switzerland)\)\s*$")


def _compile(rules):
    return [(re.compile(p, re.I), a, b) for p, a, b in rules]


_TOPICS, _OFF = _compile(TOPICS), _compile(OFF_TOPICS)
_TYPES = [(re.compile(p, re.I), adj, label) for p, adj, label in TYPE_ADJ]


def _label(rx: re.Pattern, text: str) -> str:
    m = rx.search(text)
    return m.group(0).strip().lower() if m else ""


def category(title: str, source: str, text: str) -> str:
    if re.search(r"(?i)\bph\.?d\b|promovend|doctoral\s+candidate", title):
        return "phd"
    if source in NATURE_SOURCES:
        return "conservation_zoo_ngo"
    if source in INDUSTRY_SOURCES:
        return "industry"
    if re.search(r"(?i)technician|technicus|analist|analyst|laborant|assistant|assistent|onderzoeker|"
                 r"researcher|scientist|lab\b", title):
        return "technician_research"
    if re.search(r"(?i)\bzoo\b|dierentuin|natuur|nature|conservation|wildlife", title + " " + text[:1500]):
        return "conservation_zoo_ngo"
    return "other"


def summary(text: str, limit: int = 220) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    dot = cut.rfind(". ")
    return (cut[: dot + 1] if dot > 80 else cut.rsplit(" ", 1)[0] + "…")


def score(job: Job) -> dict:
    title, text = job.title, job.description or ""
    t_pts, d_pts, hits = 0.0, 0.0, []
    for rx, in_title, in_desc in _TOPICS:
        if rx.search(title):
            t_pts += in_title
            hits.append(_label(rx, title))
        elif rx.search(text):
            d_pts += in_desc
            hits.append(_label(rx, text))
    # A relevant title matters most; words deep in the ad text can only add a little.
    raw = min(t_pts + min(d_pts, DESC_CAP), 9.0)

    minus = []
    for rx, in_title, in_desc in _OFF:
        if rx.search(title):
            raw -= in_title
            minus.append(_label(rx, title))
        elif in_desc and len(rx.findall(text)) >= 3:   # only if it's a recurring theme
            raw -= in_desc
            minus.append(_label(rx, text))

    types = []
    for rx, adj, label in _TYPES:
        if rx.search(title):
            raw += adj
            types.append(label)
    if job.source in NATURE_SOURCES:
        raw += 1
        types.append("nature organisation")

    is_phd_position = "PhD position" in types
    blockers = []
    if not is_phd_position and PHD_REQUIRED.search(text):
        blockers.append("PhD degree seems required")
    if DVM_REQUIRED.search(text) and not hits:
        blockers.append("vet/medical degree seems required")
    years = [int(n) for n in YEARS_EXP.findall(text) if 0 < int(n) < 30]
    if years and max(years) >= 3:
        blockers.append(f"{max(years)}+ years of experience asked")

    if DUTCH_FLUENT.search(text):
        dutch = "fluent"
    elif re.search(r"(?i)\b(de|het|een|en|van|voor|wij|jij)\b.*\b(de|het|een|en|van|voor|wij|jij)\b", text[:400]) \
            and len(re.findall(r"(?i)\b(de|het|een|en|van|wij|jij|je)\b", text[:1500])) > 25:
        dutch = "fluent"   # ad itself is written in Dutch
    elif DUTCH_ANY.search(text):
        dutch = "basic"
    else:
        dutch = "no"

    raw -= 2 * len(blockers)
    if dutch == "fluent":
        raw -= 0.5
    fit = max(0, min(10, int(raw + 0.5)))

    in_nl = not FOREIGN_IN_TITLE.search(title)
    if not in_nl:
        fit = min(fit, 2)

    why = []
    if hits:
        why.append("Matches: " + ", ".join(dict.fromkeys(h for h in hits if h)))
    if types:
        why.append(", ".join(types))
    if minus:
        why.append("Off-profile: " + ", ".join(dict.fromkeys(m for m in minus if m)))

    return {
        "fit_score": fit,
        "category": category(title, job.source, text),
        "summary": summary(text),
        "why": " · ".join(why),
        "blockers": blockers,
        "dutch_required": dutch,
        "deadline": job.deadline or find_deadline(text),
        "in_netherlands": in_nl,
        "model": "keywords",
    }
