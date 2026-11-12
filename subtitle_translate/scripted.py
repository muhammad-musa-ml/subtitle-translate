"""A stand-in model that knows the correct translation and breaks it in
chosen, labelled ways.

It is not a translator and it does not model how a real model fails. The
rates are mine. What it gives is ground truth: every output is logged with the
fault it carries, so a check can be scored against what was really wrong.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, fields
from typing import Dict, List, Optional

from .checks import strip_markup
from .model import Reply, Request
from .synth import NOUNS

CUE_FAULTS = ("drop", "duplicate", "merge", "number", "tag", "long", "english", "commentary", "wrong_noun")
# Faults that keep the reply parseable and the shape right, so a retry is the only cure.
STUBBORN_FAULTS = ("number", "long", "english", "commentary", "wrong_noun")


@dataclass(frozen=True)
class Rates:
    drop: float = 0.03
    duplicate: float = 0.02
    merge: float = 0.02
    number: float = 0.04
    tag: float = 0.04
    long: float = 0.04
    english: float = 0.03
    commentary: float = 0.03
    wrong_noun: float = 0.03
    fenced: float = 0.05      # whole reply wrapped in a code fence (still readable)
    truncated: float = 0.03   # whole reply cut off (not readable)
    stubborn: float = 0.03    # share of cues that carry the same fault on every attempt

    def asdict(self) -> Dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


_DIGITS = re.compile(r"\d+")
_SWAP = {}
for _i, (_en, _it, _cap) in enumerate(NOUNS):
    _nxt = NOUNS[(_i + 1) % len(NOUNS)]
    _SWAP[_it] = _nxt[1]
    _SWAP[_cap] = _nxt[2]
_SWAP_RE = re.compile("|".join(re.escape(k) for k in sorted(_SWAP, key=len, reverse=True)))


def _wrong_noun(text: str) -> Optional[str]:
    m = _SWAP_RE.search(text)
    if not m:
        return None
    return text[:m.start()] + _SWAP[m.group(0)] + text[m.end():]


class ScriptedModel:
    def __init__(self, reference: Dict[str, str], seed: int, rates: Rates = Rates()):
        self.reference = reference
        self.seed = seed
        self.rates = rates
        self.calls = 0
        self.asked: Dict[int, int] = {}
        self.log: List[dict] = []

    def _rng(self, *key) -> random.Random:
        return random.Random("%s:%s" % (self.seed, ":".join(str(k) for k in key)))

    def _fault_for(self, cue_id: int, attempt: int) -> Optional[str]:
        stub = self._rng("stubborn", cue_id)
        if stub.random() < self.rates.stubborn:
            return stub.choice(STUBBORN_FAULTS)
        r = self._rng("fault", cue_id, attempt).random()
        edge = 0.0
        for name in CUE_FAULTS:
            edge += getattr(self.rates, name)
            if r < edge:
                return name
        return None

    def translate(self, req: Request) -> Reply:
        self.calls += 1
        call = self.calls
        emitted: List[dict] = []
        entries: List[dict] = []
        merged_away = set()
        for pos, (cue_id, src) in enumerate(req.cues):
            self.asked[cue_id] = self.asked.get(cue_id, 0) + 1
            entry = {"call": call, "id": cue_id, "attempt": self.asked[cue_id], "fault": None, "batch_fault": None}
            entries.append(entry)
            if cue_id in merged_away:
                entry["fault"] = "merged_away"
                continue
            base = self.reference[src]
            text = base
            fault = self._fault_for(cue_id, entry["attempt"])
            if fault == "drop":
                entry["fault"] = "drop"
                continue
            if fault == "merge" and pos + 1 < len(req.cues):
                nxt_id, nxt_src = req.cues[pos + 1]
                text = base + "\n" + self.reference[nxt_src]
                merged_away.add(nxt_id)
                entry["fault"] = "merge"
            elif fault == "number":
                m = _DIGITS.search(base)
                if m:
                    text = base[:m.start()] + str(int(m.group()) + 1) + base[m.end():]
                    entry["fault"] = "number"
            elif fault == "tag":
                stripped = strip_markup(base)
                if stripped != base:
                    text, entry["fault"] = stripped, "tag"
            elif fault == "long":
                text, entry["fault"] = base + " " + base, "long"
            elif fault == "english":
                text, entry["fault"] = src, "english"
            elif fault == "commentary":
                text, entry["fault"] = "Ecco la traduzione: " + base, "commentary"
            elif fault == "wrong_noun":
                swapped = _wrong_noun(base)
                if swapped is not None:
                    text, entry["fault"] = swapped, "wrong_noun"
            emitted.append({"id": cue_id, "text": text})
            if fault == "duplicate":
                emitted.append({"id": cue_id, "text": text})
                entry["fault"] = "duplicate"
        payload = json.dumps(emitted, ensure_ascii=False)
        batch = self._rng("batch", call).random()
        if batch < self.rates.truncated:
            payload = payload[: int(len(payload) * 0.6)]
            for e in entries:
                e["fault"], e["batch_fault"] = "truncated", "truncated"
        elif batch < self.rates.truncated + self.rates.fenced:
            payload = "```json\n" + payload + "\n```"
            for e in entries:
                e["batch_fault"] = "fenced"
        self.log.extend(entries)
        latency = 0.35 + 0.045 * len(req.cues) + self._rng("latency", call).random() * 0.2
        return Reply(payload, latency)
