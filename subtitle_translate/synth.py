"""Seeded English subtitle files with a known correct Italian translation.

The translation is written beside the English by the same templates, so the
reference is right by construction. A scripted model can then be wrong in
chosen ways and the answer is still known.
"""
from __future__ import annotations

import random
from typing import Dict, List, Tuple

from .srt import Cue

# (English noun, Italian with article, Italian with capitalised article)
NOUNS = [
    ("player", "il player", "Il player"),
    ("editor", "l'editor", "L'editor"),
    ("export", "l'export", "L'export"),
    ("timeline", "la timeline", "La timeline"),
    ("clip", "la clip", "La clip"),
    ("upload", "l'upload", "L'upload"),
    ("template", "il template", "Il template"),
    ("preview", "l'anteprima", "L'anteprima"),
    ("render", "il render", "Il render"),
    ("project", "il progetto", "Il progetto"),
    ("folder", "la cartella", "La cartella"),
    ("caption track", "la traccia dei sottotitoli", "La traccia dei sottotitoli"),
]

# (English, Italian). {the}/{The} and {il}/{Il} take a noun; {n} and {m} take a number.
TEMPLATES: List[Tuple[str, str]] = [
    ("{The} takes {n} seconds.", "{Il} richiede {n} secondi."),
    ("We saved {the} in {n} steps.", "Abbiamo salvato {il} in {n} passaggi."),
    ("Open {the} first.", "Apri prima {il}."),
    ("<i>Wait for {the}.</i>", "<i>Aspetta {il}.</i>"),
    ("- Did you check {the}?\n- Yes, twice.", "- Hai controllato {il}?\n- Sì, due volte."),
    ("[MUSIC]", "[MUSICA]"),
    ("Step {n} of {m}.", "Passaggio {n} di {m}."),
    ("It costs {n} dollars a month.", "Costa {n} dollari al mese."),
    ("We keep {the} for {n} days.", "Conserviamo {il} per {n} giorni."),
    ("Nobody waited more than {n} minutes.", "Nessuno ha aspettato più di {n} minuti."),
    ("Press the button, then look at {the}.", "Premi il pulsante, poi guarda {il}."),
    ("We built this over {n} weeks,\nand it shows.", "L'abbiamo costruito in {n} settimane,\ne si vede."),
    ("{The} was {n} percent faster.", "{Il} è stato più veloce del {n} per cento."),
    ("Add {n} clips to the timeline.", "Aggiungi {n} clip alla timeline."),
]

MAX_LINE = 42


def _number(rng: random.Random) -> Tuple[str, str]:
    kind = rng.choice(["int", "int", "decimal", "thousands"])
    if kind == "int":
        v = str(rng.randint(2, 99))
        return v, v
    if kind == "decimal":
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        return "%d.%d" % (a, b), "%d,%d" % (a, b)
    t = rng.randint(1000, 9999)
    return "%d,%03d" % divmod(t, 1000), "%d.%03d" % divmod(t, 1000)


def _wrap(text: str) -> str:
    """Break a long single line in two at a space, or return it unchanged."""
    if "\n" in text:
        return text
    plain_len = len(_plain(text))
    if plain_len <= MAX_LINE:
        return text
    words = text.split(" ")
    for cut in range(len(words) - 1, 0, -1):
        a, b = " ".join(words[:cut]), " ".join(words[cut:])
        if len(_plain(a)) <= MAX_LINE and len(_plain(b)) <= MAX_LINE:
            return a + "\n" + b
    return text


def _plain(text: str) -> str:
    out, depth = [], 0
    for ch in text:
        if ch in "<{":
            depth += 1
        elif ch in ">}" and depth:
            depth -= 1
        elif not depth:
            out.append(ch)
    return "".join(out)


def _render(rng: random.Random) -> Tuple[str, str]:
    en_t, it_t = rng.choice(TEMPLATES)
    noun = rng.choice(NOUNS)
    n_en, n_it = _number(rng)
    m = str(rng.randint(3, 12))
    en = en_t.format(the="the " + noun[0], The="The " + noun[0], n=n_en, m=m)
    it = it_t.format(il=noun[1], Il=noun[2], n=n_it, m=m)
    return en, it


def _ok_lines(it: str) -> bool:
    lines = it.split("\n")
    return len(lines) <= 2 and all(len(_plain(x)) <= MAX_LINE for x in lines)


def generate(seed: int, n_cues: int = 60) -> Tuple[List[Cue], Dict[str, str]]:
    """English cues and {english text: correct italian text}."""
    rng = random.Random(seed)
    cues: List[Cue] = []
    reference: Dict[str, str] = {}
    t = 1000
    while len(cues) < n_cues:
        en, it = _render(rng)
        if "\n" not in en and rng.random() < 0.2:
            en2, it2 = _render(rng)
            if "\n" not in en2 and "\n" not in it and "\n" not in it2:
                if len(_plain(it)) <= MAX_LINE and len(_plain(it2)) <= MAX_LINE:
                    en, it = en + "\n" + en2, it + "\n" + it2
        if "\n" not in it:
            it = _wrap(it)
            en = _wrap(en)
        if not _ok_lines(it) or reference.get(en, it) != it:
            continue
        reference[en] = it
        chars = len(_plain(it).replace("\n", " "))
        dur_ms = int(max(1.2, chars / rng.uniform(10.0, 15.0)) * 1000)
        dur_ms = min(dur_ms, 7000)
        start = t + rng.randint(100, 1200)
        cues.append(Cue(len(cues) + 1, start, start + dur_ms, en))
        t = start + dur_ms
    return cues, reference
