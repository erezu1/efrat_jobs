"""Cheap keyword prefilter, so Claude only scores plausibly-relevant ads."""
from __future__ import annotations

import re

from .sources.base import Job

# Life-science signal anywhere in title or description (EN + NL).
POSITIVE = re.compile(r"""(?ix)
    genet | genom | \bDNA\b | e-?DNA | sequenc | bioinformat | molecul |
    ecolog | evolution | evolutie | biodivers | conservation | natuurbehoud | natuur |
    wildlife | \bzoo\b | dierentuin | zoolog | fauna | \bspecies\b | soorten |
    endangered | bedreigd | populat | breeding | fokkerij | fokprogramma |
    \banimal | \bdier | \bfish | \bvis\b | vissen | aquacult | aquacultuur | marine | mariene |
    biolog | life\s?science | laborator | \blab\b | analist | \bPCR\b | microbiol |
    veterin | ornitholog | entomolog | herpetolog | ichthyolog | limnolog
""")

# Title patterns that make a job clearly unsuitable (need a PhD / wrong profession).
EXCLUDE_TITLE = re.compile(r"""(?ix)
    post-?doc | postdoctoral | \bprofessor | hoogleraar | \blector\b | tenure[\s-]?track |
    universitair\s+(hoofd)?docent | \bUD\b | \bUHD\b |
    dierenartsassistent | paraveterinair | vet(erinary)?\s+(assistant|nurse|technician) |
    \bdierenarts\b | veterinarian | \bphysician | \barts\b | verpleegkundig | \bnurse\b |
    pharmacist | apotheker |
    \binternship | \bstagiair | \bstageplaats | afstudeer | master\s+thesis | \bMSc\s+thesis |
    bachelor\s+thesis | vrijwillig | \bvolunteer
""")


def prefilter(job: Job, domain_specific: bool = False) -> tuple[bool, str]:
    """Return (passes, reason). domain_specific sources skip the positive-keyword check."""
    if EXCLUDE_TITLE.search(job.title):
        return False, f"title excluded ({EXCLUDE_TITLE.search(job.title).group(0).strip()})"
    if domain_specific:
        return True, "domain-specific source"
    m = POSITIVE.search(job.title + "\n" + job.description)
    if not m:
        return False, "no life-science keywords"
    return True, f"keyword: {m.group(0).strip()}"
