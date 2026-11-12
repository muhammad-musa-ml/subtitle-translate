"""Command line: python -m subtitle_translate translate IN.srt --to Italian --out OUT.srt"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import pipeline, srt
from .checks import Rules
from .model import OpenAIChat


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="subtitle_translate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("translate", help="translate an .srt file and check every cue")
    t.add_argument("source")
    t.add_argument("--to", required=True, help="target language name, for example Italian")
    t.add_argument("--out", required=True)
    t.add_argument("--report", help="write a JSON report here")
    t.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    t.add_argument("--model", required=True)
    t.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "none"))
    t.add_argument("--temperature", type=float, default=0.0)
    t.add_argument("--timeout", type=float, default=120.0)
    t.add_argument("--batch", type=int, default=8)
    t.add_argument("--retries", type=int, default=2)
    t.add_argument("--max-lines", type=int, default=Rules.max_lines)
    t.add_argument("--max-line-chars", type=int, default=Rules.max_line_chars)
    t.add_argument("--max-cps", type=float, default=Rules.max_cps)
    t.add_argument("--force", action="store_true", help="overwrite --out and --report if they exist")
    return ap


def bad_setting(a: argparse.Namespace) -> str:
    """The first setting that cannot work, as a sentence, or an empty string."""
    for name, ok in (("--batch", a.batch >= 1), ("--retries", a.retries >= 0), ("--max-lines", a.max_lines >= 1),
                     ("--max-line-chars", a.max_line_chars >= 1), ("--max-cps", a.max_cps > 0),
                     ("--timeout", a.timeout > 0)):
        if not ok:
            return "%s is out of range" % name
    return ""


def run_translate(a: argparse.Namespace) -> int:
    problem = bad_setting(a)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    for path in (a.out, a.report):
        if path and os.path.exists(path) and not a.force:
            print("%s exists; pass --force to overwrite it" % path, file=sys.stderr)
            return 2
    try:
        with open(a.source, encoding="utf-8") as fh:
            cues = srt.parse(fh.read())
    except (OSError, UnicodeDecodeError, srt.SrtError) as exc:
        print("cannot read %s: %s" % (a.source, exc), file=sys.stderr)
        return 2
    rules = Rules(max_lines=a.max_lines, max_line_chars=a.max_line_chars, max_cps=a.max_cps)
    client = OpenAIChat(a.base_url, a.model, a.api_key, a.timeout, a.temperature)
    result = pipeline.translate(cues, client, a.to, rules, a.batch, a.retries)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(srt.format(result.translated(cues)))
    summary = result.summary()
    if a.report:
        report = dict(summary)
        report["left_in_source"] = [r.index for r in result.cues if r.status == "fallback"]
        report["rejected"] = [r for r in result.attempt_log if r["codes"]]
        with open(a.report, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    print("%(cues)d cues, %(calls)d calls, status %(status)s" % summary, file=sys.stderr)
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return run_translate(a)
