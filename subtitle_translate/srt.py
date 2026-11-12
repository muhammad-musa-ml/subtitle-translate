"""Read and write SubRip (.srt) subtitle files."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


class SrtError(ValueError):
    """A subtitle file that cannot be read; the message names the line."""


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_s(self) -> float:
        return (self.end_ms - self.start_ms) / 1000.0


_TS = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})$")


def ts_to_ms(ts: str) -> int:
    m = _TS.match(ts.strip())
    if not m:
        raise ValueError("bad timestamp: %r" % ts)
    h, mi, s, ms = (int(x) for x in m.groups())
    if mi > 59 or s > 59:
        raise ValueError("bad timestamp: %r" % ts)
    return ((h * 60 + mi) * 60 + s) * 1000 + ms


def ms_to_ts(ms: int) -> str:
    h, rest = divmod(ms, 3_600_000)
    m, rest = divmod(rest, 60_000)
    s, milli = divmod(rest, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, milli)


def parse(text: str) -> List[Cue]:
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    n = len(lines)
    cues: List[Cue] = []
    seen = set()
    i = 0
    while i < n:
        if not lines[i].strip():
            i += 1
            continue
        try:
            index = int(lines[i].strip())
        except ValueError:
            raise SrtError("line %d: expected a cue number, got %r" % (i + 1, lines[i]))
        i += 1
        if i >= n or "-->" not in lines[i]:
            raise SrtError("line %d: expected a timing line after cue %d" % (i + 1, index))
        left, _, right = lines[i].partition("-->")
        tokens = right.split()
        if not tokens:
            raise SrtError("line %d: no end time for cue %d" % (i + 1, index))
        try:
            start, end = ts_to_ms(left), ts_to_ms(tokens[0])
        except ValueError as exc:
            raise SrtError("line %d: %s" % (i + 1, exc))
        if end <= start:
            raise SrtError("line %d: cue %d ends before it starts" % (i + 1, index))
        if index in seen:
            raise SrtError("line %d: cue number %d appears twice" % (i, index))
        seen.add(index)
        i += 1
        body = []
        while i < n and lines[i].strip():
            body.append(lines[i])
            i += 1
        cues.append(Cue(index, start, end, "\n".join(body)))
    return cues


def format(cues: List[Cue]) -> str:
    blocks = []
    for c in cues:
        blocks.append("%d\n%s --> %s\n%s\n" % (c.index, ms_to_ts(c.start_ms), ms_to_ts(c.end_ms), c.text))
    return "\n".join(blocks)
