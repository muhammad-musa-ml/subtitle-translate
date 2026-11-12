"""Measurements: the scripted stand-in (ground truth known) and a live model.

  python -m subtitle_translate.bench standin            write results/standin.json and .md
  python -m subtitle_translate.bench live --model NAME  write results/live-NAME.json and .md
  python -m subtitle_translate.bench readme             copy the generated tables into README.md
  python -m subtitle_translate.bench check              fail if results and README disagree
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from typing import Dict, List

from . import pipeline, srt, synth
from .checks import Rules
from .model import OpenAIChat
from .scripted import CUE_FAULTS, Rates, ScriptedModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
README = os.path.join(ROOT, "README.md")
SEEDS = (1, 2, 3, 4, 5)
FILES_PER_SEED = 3
CUES_PER_FILE = 60
BATCH = 8
RETRIES = 2
KINDS = CUE_FAULTS + ("merged_away", "truncated")


def _bump(d: Dict[str, int], key: str, n: int = 1) -> None:
    d[key] = d.get(key, 0) + n


def score_run(result: pipeline.Result, log: List[dict]) -> Dict[str, object]:
    by = {(e["call"], e["id"]): e for e in log}
    first = {e["id"]: e for e in log if e["attempt"] == 1}
    s: Dict[str, object] = {
        "cues": 0, "first_reply_clean": 0, "first_reply_wrong": 0, "shipped_right": 0,
        "shipped_wrong": 0, "left_in_source": 0, "reflowed": 0, "first_reply_wrong_by": {},
        "shipped_wrong_by": {}, "trials": {}, "rejected": {},
    }
    for r in result.cues:
        if r.status == "passthrough":
            continue
        s["cues"] += 1
        fault = first[r.index]["fault"]
        if fault is None:
            s["first_reply_clean"] += 1
        else:
            s["first_reply_wrong"] += 1
            _bump(s["first_reply_wrong_by"], fault)
        if r.status == "fallback":
            s["left_in_source"] += 1
            continue
        s["reflowed"] += 1 if r.reflowed else 0
        shipped = by[(r.accepted_call, r.index)]["fault"]
        if shipped is None:
            s["shipped_right"] += 1
        else:
            s["shipped_wrong"] += 1
            _bump(s["shipped_wrong_by"], shipped)
    for row in result.attempt_log:
        kind = by[(row["call"], row["index"])]["fault"] or "clean"
        _bump(s["trials"], kind)
        if row["codes"]:
            _bump(s["rejected"], kind)
    s["calls_first_reply"] = result.round_calls[0] if result.round_calls else 0
    s["calls_with_retries"] = result.calls
    s["latency_first_reply_s"] = sum(result.call_latency[n] for n in range(1, s["calls_first_reply"] + 1))
    s["latency_with_retries_s"] = result.latency_s
    return s


def _add(total: Dict[str, object], part: Dict[str, object]) -> None:
    for k, v in part.items():
        if isinstance(v, dict):
            sub = total.setdefault(k, {})
            for kk, vv in v.items():
                sub[kk] = sub.get(kk, 0) + vv
        else:
            total[k] = total.get(k, 0) + v


def run_standin(seeds=SEEDS, files=FILES_PER_SEED, cues_per_file=CUES_PER_FILE, rates: Rates = Rates(),
                batch=BATCH, retries=RETRIES, rules: Rules = Rules()) -> dict:
    per_seed, pooled = [], {}
    for seed in seeds:
        row: Dict[str, object] = {}
        for f in range(files):
            run_seed = seed * 100 + f
            cues, reference = synth.generate(run_seed, cues_per_file)
            model = ScriptedModel(reference, run_seed, rates)
            result = pipeline.translate(cues, model, "Italian", rules, batch, retries)
            _add(row, score_run(result, model.log))
        per_seed.append({"seed": seed, **row})
        _add(pooled, row)
    return {
        "setup": {
            "seeds": list(seeds), "files_per_seed": files, "cues_per_file": cues_per_file,
            "batch_size": batch, "max_retries": retries, "rates": rates.asdict(),
        },
        "per_seed": per_seed,
        "pooled": pooled,
    }


def _pct(a: int, b: int) -> str:
    return "n/a" if b == 0 else "%.0f%%" % (100.0 * a / b)


def render_standin(d: dict) -> str:
    p = d["pooled"]
    out = ["Cues per seed: %d files of %d cues. Latency is the stand-in's scripted time, not a measurement." % (
        d["setup"]["files_per_seed"], d["setup"]["cues_per_file"]), ""]
    out += ["| seed | cues | first reply wrong | shipped right | shipped wrong | left in English | calls, first replies / with retries |",
            "|---|---|---|---|---|---|---|"]
    for r in d["per_seed"] + [dict(p, seed="all")]:
        out.append("| %s | %d | %d (%s) | %d | %d | %d | %d / %d |" % (
            r["seed"], r["cues"], r["first_reply_wrong"], _pct(r["first_reply_wrong"], r["cues"]),
            r["shipped_right"], r["shipped_wrong"], r["left_in_source"],
            r["calls_first_reply"], r["calls_with_retries"]))
    out += ["", "Scripted latency over all seeds: %.0f s for first replies only, %.0f s with retries. "
            "Cues whose line breaks reflow moved: %d." % (
                p["latency_first_reply_s"], p["latency_with_retries_s"], p["reflowed"]), ""]
    out += ["| fault in the output | times it occurred | rejected by the checks | share rejected | shipped anyway |",
            "|---|---|---|---|---|"]
    for k in KINDS:
        n = p["trials"].get(k, 0)
        if n:
            out.append("| %s | %d | %d | %s | %d |" % (
                k, n, p["rejected"].get(k, 0), _pct(p["rejected"].get(k, 0), n), p["shipped_wrong_by"].get(k, 0)))
    n = p["trials"].get("clean", 0)
    out += ["", "Outputs with no fault: %d, rejected by the checks: %d (%s)." % (
        n, p["rejected"].get("clean", 0), _pct(p["rejected"].get("clean", 0), n))]
    return "\n".join(out) + "\n"


def run_live(source: str, base_url: str, model: str, runs: int, temperature: float,
             target: str, batch: int, retries: int, rules: Rules = Rules()) -> dict:
    with open(source, encoding="utf-8") as fh:
        cues = srt.parse(fh.read())
    rows = []
    for run in range(1, runs + 1):
        client = OpenAIChat(base_url, model, temperature=temperature, seed=run)
        started = time.monotonic()
        result = pipeline.translate(cues, client, target, rules, batch, retries)
        wall = time.monotonic() - started
        text = {c.index: c.text for c in cues}
        rejected = [
            dict({"index": r["index"], "attempt": r["attempt"], "codes": r["codes"], "source": text[r["index"]],
                  "output": r["text"]}, **({"error": r["error"]} if "error" in r else {}))
            for r in result.attempt_log if r["codes"]
        ]
        rows.append({"run": run, "seed": run, "wall_s": round(wall, 1), "summary": result.summary(),
                     "rejected": rejected})
    return {
        "setup": {"source": os.path.basename(source), "model": model, "target": target, "runs": runs,
                  "temperature": temperature, "batch_size": batch, "max_retries": retries},
        "runs": rows,
    }


def render_live(d: dict) -> str:
    s = d["setup"]
    out = ["Model `%s`, English to %s, `%s`, %d runs (sampling seed = run number, temperature %s)." % (
        s["model"], s["target"], s["source"], s["runs"], s["temperature"]), "",
        "| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |",
        "|---|---|---|---|---|---|---|"]
    for r in d["runs"]:
        sm = r["summary"]
        first = sum(1 for x in r["rejected"] if x["attempt"] == 1)
        st = sm["status"]
        out.append("| %d | %d | %d | %d / %d / %d | %d | %d | %d |" % (
            r["run"], sm["cues"], first, st.get("ok", 0), st.get("retried", 0), st.get("fallback", 0),
            sm["reflowed"], sm["calls"], round(r["wall_s"])))
    codes: Dict[str, int] = {}
    for r in d["runs"]:
        for k, v in r["summary"]["first_attempt_codes"].items():
            codes[k] = codes.get(k, 0) + v
    out += ["", "Why first replies were rejected, all runs: " + (
        ", ".join("%s %d" % kv for kv in sorted(codes.items(), key=lambda kv: -kv[1])) or "nothing was rejected") + "."]
    return "\n".join(out) + "\n"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _write_json(path: str, data: dict) -> None:
    _write(path, json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def _block(name: str, body: str) -> str:
    return "<!-- %s:start -->\n\n%s\n<!-- %s:end -->" % (name, body.rstrip("\n") + "\n", name)


def _readme_blocks() -> Dict[str, str]:
    blocks = {}
    path = os.path.join(RESULTS, "standin.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            blocks["standin"] = render_standin(json.load(fh))
    live = []
    for p in sorted(glob.glob(os.path.join(RESULTS, "live-*.json"))):
        with open(p, encoding="utf-8") as fh:
            live.append(render_live(json.load(fh)))
    if live:
        blocks["live"] = "\n".join(live)
    return blocks


def write_readme() -> None:
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    for name, body in _readme_blocks().items():
        pat = re.compile(r"<!-- %s:start -->.*?<!-- %s:end -->" % (name, name), re.S)
        if not pat.search(text):
            raise SystemExit("README has no %s block" % name)
        text = pat.sub(lambda m: _block(name, body), text)
    _write(README, text)


def check() -> int:
    problems = []
    path = os.path.join(RESULTS, "standin.json")
    with open(path, encoding="utf-8") as fh:
        stored = json.load(fh)
    s = stored["setup"]
    fresh = run_standin(tuple(s["seeds"]), s["files_per_seed"], s["cues_per_file"], Rates(**s["rates"]),
                        s["batch_size"], s["max_retries"])
    if json.loads(json.dumps(fresh)) != stored:
        problems.append("results/standin.json differs from a fresh run")
    with open(README, encoding="utf-8") as fh:
        text = fh.read()
    for name, body in _readme_blocks().items():
        if _block(name, body) not in text:
            problems.append("README %s block differs from results/" % name)
    for p in problems:
        print(p)
    print("ok" if not problems else "%d problem(s)" % len(problems))
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="subtitle_translate.bench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("standin")
    lv = sub.add_parser("live")
    lv.add_argument("--model", required=True)
    lv.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    lv.add_argument("--source", default=os.path.join(ROOT, "samples", "demo.srt"))
    lv.add_argument("--target", default="Italian")
    lv.add_argument("--runs", type=int, default=3)
    lv.add_argument("--temperature", type=float, default=0.3)
    sub.add_parser("readme")
    sub.add_parser("check")
    a = ap.parse_args(argv)
    if a.cmd == "standin":
        d = run_standin()
        _write_json(os.path.join(RESULTS, "standin.json"), d)
        _write(os.path.join(RESULTS, "standin.md"), render_standin(d))
        print(render_standin(d))
    elif a.cmd == "live":
        d = run_live(a.source, a.base_url, a.model, a.runs, a.temperature, a.target, BATCH, RETRIES)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", a.model)
        _write_json(os.path.join(RESULTS, "live-%s.json" % safe), d)
        _write(os.path.join(RESULTS, "live-%s.md" % safe), render_live(d))
        print(render_live(d))
    elif a.cmd == "readme":
        write_readme()
    else:
        return check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
