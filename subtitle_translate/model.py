"""The model interface: what is asked, what comes back, and a client for any
server that speaks the OpenAI chat completions API (Ollama does)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .checks import Rules


class ModelError(Exception):
    """The call failed (connection, timeout, HTTP error, unusable reply body)."""


@dataclass
class Request:
    target: str
    cues: List[Tuple[int, str]]
    feedback: Dict[int, List[str]] = field(default_factory=dict)
    rules: Rules = field(default_factory=Rules)


@dataclass
class Reply:
    text: str
    latency_s: float


PROBLEMS = {
    "empty": "the translation was empty",
    "structure": "it had a blank line inside the cue or contained an arrow",
    "lines": "it had too many lines",
    "line_length": "a line was too long",
    "reading_speed": "it was too long to read in the time the cue is on screen",
    "numbers": "the numbers did not match the source",
    "tags": "the tags did not match the source",
    "dialogue": "the dialogue dashes did not match the source",
    "unchanged": "it was the source text, untranslated",
    "english_left": "it was still partly in English",
    "commentary": "it had a note or an introduction around the translation",
    "length_ratio": "its length was far from the source",
    "missing": "the cue was missing from the reply",
    "duplicate": "the cue appeared more than once in the reply",
    "bad_reply": "the reply was not the JSON array that was asked for",
    "model_error": "the call failed",
}


def parse_reply(raw: str) -> Tuple[Optional[list], bool]:
    """(items, repaired). `items` is None when no JSON array of objects is found.

    A reply wrapped in a code fence or in a sentence is read from its first
    '[' to its last ']' and reported as repaired.
    """
    try:
        data = json.loads(raw)
        repaired = False
    except ValueError:
        start, end = raw.find("["), raw.rfind("]")
        if start < 0 or end <= start:
            return None, False
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            return None, False
        repaired = True
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        return None, False
    return data, repaired


def build_messages(req: Request) -> List[dict]:
    r = req.rules
    system = (
        "You translate subtitle cues from English into %s. Reply with one JSON array and nothing else. "
        "Each item is {\"id\": number, \"text\": string}, one item for each cue you are given, in the same order. "
        "Write a line break inside a text the way JSON does. Copy every number and every tag such as <i> "
        "exactly as it appears in the source. Add no notes. A cue may have at most %d line%s of %d characters."
        % (req.target, r.max_lines, "" if r.max_lines == 1 else "s", r.max_line_chars)
    )
    user = json.dumps([{"id": i, "text": t} for i, t in req.cues], ensure_ascii=False)
    if req.feedback:
        notes = [
            {"id": i, "problems": [PROBLEMS.get(c, c) for c in codes]}
            for i, codes in sorted(req.feedback.items())
        ]
        user += "\n\nThese cues were rejected last time. Fix the problems:\n" + json.dumps(notes, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


class OpenAIChat:
    def __init__(self, base_url: str, model: str, api_key: str = "none",
                 timeout_s: float = 120.0, temperature: float = 0.0, seed: Optional[int] = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.seed = seed

    def translate(self, req: Request) -> Reply:
        body = {
            "model": self.model,
            "messages": build_messages(req),
            "temperature": self.temperature,
            "stream": False,
        }
        if self.seed is not None:
            body["seed"] = self.seed
        http = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The status line alone ("500") hides the reason; servers put it in the body.
            try:
                detail = exc.read().decode("utf-8", "replace").strip()[:300]
            except OSError:
                detail = ""
            raise ModelError("HTTP %d: %s" % (exc.code, detail or exc.reason))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ModelError(str(exc))
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ModelError("unexpected reply shape")
        if not isinstance(content, str):
            raise ModelError("reply content is not text")
        return Reply(content, time.monotonic() - started)
