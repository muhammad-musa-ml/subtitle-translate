"""Re-break the lines of a translated cue so that they fit.

A model does not count characters, so a correct translation often comes back
as one line that is a few characters too long. Asking again rarely helps; the
words are right and only the line break is wrong. This changes line breaks and
joins the words with single spaces; it touches nothing else.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .checks import Rules, strip_markup

# A word is a run of non-space characters; a tag such as <font color="red"> stays whole.
_WORD = re.compile(r"(?:<[^>]*>|\{[^}]*\}|\S)+")
_INF = 10 ** 9


def _split(widths: List[int], k: int, limit: int) -> Optional[List[Tuple[int, int]]]:
    """Cut the words into exactly k lines, each at most `limit` wide, with the longest line as short as possible."""
    n = len(widths)
    best = [[_INF] * (n + 1) for _ in range(k + 1)]
    prev = [[0] * (n + 1) for _ in range(k + 1)]
    best[0][0] = 0
    for line in range(1, k + 1):
        for j in range(line, n + 1):
            for i in range(line - 1, j):
                width = sum(widths[i:j]) + (j - i - 1)
                if width > limit or best[line - 1][i] >= _INF:
                    continue
                longest = max(best[line - 1][i], width)
                if longest < best[line][j]:
                    best[line][j] = longest
                    prev[line][j] = i
    if best[k][n] >= _INF:
        return None
    spans, j = [], n
    for line in range(k, 0, -1):
        i = prev[line][j]
        spans.append((i, j))
        j = i
    return spans[::-1]


def reflow(text: str, rules: Rules = Rules()) -> str:
    """`text` with its line breaks moved so each line fits, or `text` unchanged.

    Unchanged when it already fits, when a dialogue dash starts a line, when it
    has a blank line, or when no layout within rules.max_lines fits.
    """
    lines = text.split("\n")
    fits = len(lines) <= rules.max_lines and all(len(strip_markup(ln)) <= rules.max_line_chars for ln in lines)
    if fits or any(not ln.strip() or ln.lstrip().startswith("-") for ln in lines):
        return text
    words = _WORD.findall(text)
    widths = [len(strip_markup(w)) for w in words]
    for k in range(1, rules.max_lines + 1):
        spans = _split(widths, k, rules.max_line_chars)
        if spans:
            return "\n".join(" ".join(words[i:j]) for i, j in spans)
    return text
