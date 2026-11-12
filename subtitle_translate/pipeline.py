"""Translate a list of cues with a model, check every cue, ask again for the
ones that fail, and fall back to the source text for the ones that never pass.

A cue is shipped only if it passed every check. One that never does keeps its
source text (status "fallback") and is listed in the report. Nothing here
depends on randomness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .checks import Rules, check_cue
from .model import ModelError, Request, parse_reply
from .reflow import reflow
from .srt import Cue

ENGLISH_NAMES = ("en", "eng", "english")


@dataclass
class CueResult:
    index: int
    status: str                      # ok | retried | fallback | passthrough
    text: str
    attempts: int = 0
    first_codes: List[str] = field(default_factory=list)
    accepted_call: Optional[int] = None
    reflowed: bool = False           # the shipped text has line breaks moved by reflow()


@dataclass
class Result:
    cues: List[CueResult]
    calls: int = 0
    latency_s: float = 0.0
    repaired_replies: int = 0
    attempt_log: List[dict] = field(default_factory=list)   # one row per cue per attempt
    call_latency: Dict[int, float] = field(default_factory=dict)
    round_calls: List[int] = field(default_factory=list)    # calls made in each round

    def translated(self, source: List[Cue]) -> List[Cue]:
        by_index = {r.index: r for r in self.cues}
        return [Cue(c.index, c.start_ms, c.end_ms, by_index[c.index].text) for c in source]

    def summary(self) -> Dict[str, object]:
        counts: Dict[str, int] = {}
        for r in self.cues:
            counts[r.status] = counts.get(r.status, 0) + 1
        first: Dict[str, int] = {}
        for r in self.cues:
            for code in r.first_codes:
                first[code] = first.get(code, 0) + 1
        return {
            "cues": len(self.cues),
            "status": counts,
            "reflowed": sum(1 for r in self.cues if r.reflowed),
            "first_attempt_codes": dict(sorted(first.items())),
            "calls": self.calls,
            "latency_s": round(self.latency_s, 3),
            "repaired_replies": self.repaired_replies,
        }


def _has_text(cue: Cue) -> bool:
    return any(ch.isalpha() for ch in cue.text)


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def translate(cues: List[Cue], model, target: str, rules: Rules = Rules(),
              batch_size: int = 8, max_retries: int = 2) -> Result:
    if batch_size < 1 or max_retries < 0:
        raise ValueError("batch_size must be at least 1 and max_retries at least 0")
    target_is_english = target.strip().lower() in ENGLISH_NAMES
    results: Dict[int, CueResult] = {}
    state: Dict[int, dict] = {}
    pending: List[Cue] = []
    for c in cues:
        if _has_text(c):
            pending.append(c)
            state[c.index] = {"attempts": 0, "first": None, "codes": []}
        else:
            results[c.index] = CueResult(c.index, "passthrough", c.text)
    out = Result(cues=[])

    for round_no in range(max_retries + 1):
        if not pending:
            break
        failed: List[Cue] = []
        calls_before = out.calls
        for batch in _chunks(pending, batch_size):
            feedback = {c.index: state[c.index]["codes"] for c in batch} if round_no else {}
            req = Request(target, [(c.index, c.text) for c in batch], feedback, rules)
            out.calls += 1
            call_no = out.calls
            texts: Dict[int, List[str]] = {}
            call_codes: Optional[List[str]] = None
            call_error: Optional[str] = None
            try:
                reply = model.translate(req)
            except ModelError as exc:
                call_codes, call_error = ["model_error"], str(exc)
            else:
                out.latency_s += reply.latency_s
                out.call_latency[call_no] = reply.latency_s
                items, repaired = parse_reply(reply.text)
                if items is None:
                    call_codes = ["bad_reply"]
                else:
                    out.repaired_replies += 1 if repaired else 0
                    for item in items:
                        cue_id, text = item.get("id"), item.get("text")
                        if type(cue_id) is int and isinstance(text, str):
                            texts.setdefault(cue_id, []).append(text.strip())
            for c in batch:
                st = state[c.index]
                st["attempts"] += 1
                if call_codes is not None:
                    codes = list(call_codes)
                elif c.index not in texts:
                    codes = ["missing"]
                elif len(texts[c.index]) > 1:
                    codes = ["duplicate"]
                else:
                    text = reflow(texts[c.index][0], rules)
                    codes = check_cue(c, text, rules, target_is_english)
                if st["first"] is None:
                    st["first"] = codes
                shown = texts[c.index][0] if len(texts.get(c.index, [])) == 1 else None
                row = {"call": call_no, "index": c.index, "attempt": st["attempts"], "codes": codes, "text": shown}
                if call_error:
                    row["error"] = call_error
                out.attempt_log.append(row)
                if codes:
                    st["codes"] = codes
                    failed.append(c)
                else:
                    results[c.index] = CueResult(
                        c.index, "ok" if st["attempts"] == 1 else "retried",
                        text, st["attempts"], st["first"], call_no, text != texts[c.index][0],
                    )
        out.round_calls.append(out.calls - calls_before)
        pending = failed

    for c in pending:
        st = state[c.index]
        results[c.index] = CueResult(c.index, "fallback", c.text, st["attempts"], st["first"])
    out.cues = [results[c.index] for c in cues]
    return out
