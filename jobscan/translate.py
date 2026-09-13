"""Translate Dutch job titles and summaries to English with a free, open-source model (OPUS-MT nl→en).

Runs inside the daily scan. Each text is translated once and cached in data/translations.json,
so after the first run only a handful of new jobs need translating. If the model libraries
aren't installed, translation is skipped and the page simply shows the original text.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "translations.json"
MODEL = "Helsinki-NLP/opus-mt-nl-en"
MAX_PER_RUN = 3000
BATCH = 16

_NL_WORDS = re.compile(r"(?i)\b(de|het|een|en|van|voor|wij|jij|je|met|zijn|naar|bij|ons|onze|als|werk|ben|bent|"
                       r"medewerker|onderzoeker|vacature|functie|uur|per|week)\b")
_EN_WORDS = re.compile(r"(?i)\b(the|and|of|for|with|you|we|our|are|is|to|in|at|position|research)\b")
# split Dutch science compounds the model otherwise mangles ("kwelderecologie" -> "kwelder ecologie")
_COMPOUND = re.compile(r"(?i)\b(\w{4,}?)(ecologie|biologie|genetica|onderzoek|onderzoeker|analist|beheer|monitoring|"
                       r"laboratorium|techniek|technieken)\b")


def key(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def is_dutch(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ]+", text or "")
    if not words:
        return False
    nl, en = len(_NL_WORDS.findall(text)), len(_EN_WORDS.findall(text))
    if len(words) <= 6:                      # short titles: typical Dutch job words
        return nl > en or bool(re.search(r"(?i)(medewerker|onderzoeker|analist|laborant|beheerder|adviseur|"
                                         r"coördinator|ecoloog|promovendus|stagiair|verzorger|assistent)\b", text))
    return nl >= 2 and nl > en


def load() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def update(texts: list[str]) -> dict:
    cache = load()
    todo = list(dict.fromkeys(t for t in texts if t and is_dutch(t) and key(t) not in cache))[:MAX_PER_RUN]
    if todo:
        try:
            from transformers import MarianMTModel, MarianTokenizer
        except ImportError:
            print("translation skipped (transformers not installed)")
            return cache
        tok = MarianTokenizer.from_pretrained(MODEL)
        model = MarianMTModel.from_pretrained(MODEL)
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            prepared = [_COMPOUND.sub(r"\1 \2", t) for t in chunk]
            enc = tok(prepared, return_tensors="pt", padding=True, truncation=True, max_length=256)
            out = model.generate(**enc, num_beams=2, max_new_tokens=220)
            for src, en in zip(chunk, tok.batch_decode(out, skip_special_tokens=True)):
                cache[key(src)] = en
        print(f"translated {len(todo)} Dutch texts")
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True))
    return cache
