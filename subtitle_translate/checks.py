"""Per-cue checks on a translated subtitle. Each returns a short code.

The limits are my defaults for a readable subtitle, not a standard; change
them with Rules. A translation that passes is not necessarily right: nothing
here can tell that a noun was replaced by another one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .srt import Cue


@dataclass(frozen=True)
class Rules:
    max_lines: int = 2
    max_line_chars: int = 42
    max_cps: float = 20.0
    min_ratio: float = 0.5
    max_ratio: float = 2.0
    ratio_min_source_chars: int = 5   # a shorter source ("Hi", "OK") can grow a lot in translation


CODES = (
    "empty", "structure", "lines", "line_length", "reading_speed", "numbers", "tags", "dialogue",
    "unchanged", "english_left", "commentary", "length_ratio",
)

# A tag must close before another one opens, so an unclosed "<i" does not swallow the text after it.
_MARKUP = re.compile(r"<[^<>]*>|\{[^{}]*\}")
_DIGITS = re.compile(r"\d+")
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)

# Function words that are English and not words in Italian, French, Spanish,
# German or Portuguese, so a cue full of them was left in English.
ENGLISH_STOPWORDS = frozenset(
    ["the", "and", "is", "are", "of", "to", "that", "with", "you", "we", "this", "it", "have"]
)

# What a model adds around a translation instead of translating: an English
# opener, or a label such as "Traduzione:" near the start. A word like "Ecco"
# alone is ordinary Italian and must pass.
_COMMENTARY = re.compile(
    r"^\s*(?:(?:sure|certainly|of course)\b|note\s*:|.{0,40}\b(?:translation|translated|traduzione|traduction|traducción|übersetzung)\s*:)",
    re.IGNORECASE,
)


def strip_markup(text: str) -> str:
    return _MARKUP.sub("", text)


def markup(text: str) -> List[str]:
    return _MARKUP.findall(text)


def digit_runs(text: str) -> List[str]:
    """The runs of digits in the order they appear: "1,200" is "1" then "200", "2.5" is "2" then "5"."""
    return _DIGITS.findall(strip_markup(text))


def dialogue_lines(text: str) -> int:
    """How many lines start with a dash once tags are removed."""
    return sum(1 for ln in text.split("\n") if strip_markup(ln).lstrip().startswith("-"))


def check_cue(source: Cue, translated: str, rules: Rules = Rules(), target_is_english: bool = False) -> List[str]:
    """Codes for everything wrong with `translated` as the text of `source`."""
    if not translated.strip():
        return ["empty"]
    codes: List[str] = []
    plain = strip_markup(translated)
    src_plain = strip_markup(source.text)
    lines = translated.split("\n")
    if any(not ln.strip() for ln in lines) or "-->" in translated:
        codes.append("structure")
    if len(lines) > rules.max_lines:
        codes.append("lines")
    if any(len(strip_markup(ln)) > rules.max_line_chars for ln in lines):
        codes.append("line_length")
    chars = len(plain.replace("\n", " "))
    if chars / max(source.duration_s, 0.001) > rules.max_cps:
        codes.append("reading_speed")
    if digit_runs(translated) != digit_runs(source.text):
        codes.append("numbers")
    if markup(translated) != markup(source.text):
        codes.append("tags")
    if dialogue_lines(translated) != dialogue_lines(source.text):
        codes.append("dialogue")
    words = _WORDS.findall(plain)
    if not target_is_english and len(words) >= 3:
        if plain.strip().lower() == src_plain.strip().lower() and sum(len(w) for w in words) >= 12:
            codes.append("unchanged")
        else:
            english = sum(1 for w in words if w.lower() in ENGLISH_STOPWORDS)
            if english / len(words) > 0.3:
                codes.append("english_left")
    if _COMMENTARY.match(plain) or "```" in translated:
        codes.append("commentary")
    src_len = len(src_plain.strip())
    ratio = len(plain.strip()) / max(1, src_len)
    if src_len >= rules.ratio_min_source_chars and (ratio < rules.min_ratio or ratio > rules.max_ratio):
        codes.append("length_ratio")
    return codes
