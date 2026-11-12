# subtitle-translate

I wrote this to translate a subtitle file (.srt) with a language model and check every translated cue before it is written out. It talks to any server that speaks the OpenAI chat API (Ollama on localhost by default) and uses only the Python standard library. I ran it on Python 3.13.

Not affiliated with Bending Spoons or Vimeo.

## Why

A model that translates a file can change a number, drop an italics tag, return a line that is too long to read in the time the cue is on screen, leave a cue in English, or put "Ecco la traduzione:" in front of the text. I wanted to know how often small local models do this, and how much a per-cue check and a retry fix.

## Use

    python -m subtitle_translate translate samples/demo.srt --to Italian --model gemma3:latest --out demo.it.srt --report demo.it.json

`--base-url` points it at another server and `--force` overwrites existing files. The report lists every rejected attempt and the cues left in the source language. `--api-key` defaults to the `OPENAI_API_KEY` environment variable and is sent as a bearer token to whatever `--base-url` names. The exit code is 0 even when cues were left in the source language, so read the summary line or the report.

## What it does

- Sends cues in batches of 8 as JSON and reads a JSON array back. A reply wrapped in a code fence is accepted and counted as repaired.
- When the lines do not fit, `reflow.py` moves the line breaks, joins the words with single spaces and changes nothing else. It leaves dialogue dashes and blank lines alone.
- `checks.py` rejects a cue that is empty, has a blank line or an arrow in it, has too many lines or a line that is too long, is read too fast, changes, drops or reorders a number or a tag, loses a dialogue dash, comes back unchanged or partly in English, has a note around it, or is far longer or shorter than the source. The limits are my defaults, not a standard: 2 lines of 42 characters, 20 characters per second, a length ratio from 0.5 to 2 that is not applied to sources under 5 characters.
- Only the rejected cues are asked again, with the failed checks named in words, up to 2 more times.
- A cue that never passes keeps its source text and is listed in the report. Cues without letters are not sent.

## Tests

    python -m unittest discover -s tests -t .
    python -m subtitle_translate.bench check

The second command reruns the stand-in below and fails if `results/standin.json` or the tables in this file differ from what it computes. The live tables are copied from the stored files in `results/` and cannot be recomputed without the models.

## Measurements

### Stand-in model

`scripted.py` is not a translator. It knows the correct Italian for synthetic English cues (`synth.py`) and breaks it in labelled ways at rates I chose (`setup` in `results/standin.json`), so the fault in every output, or the lack of one, is known. Five seeds, three files of 60 cues each. Regenerate with `python -m subtitle_translate.bench standin`.

<!-- standin:start -->

Cues per seed: 3 files of 60 cues. Latency is the stand-in's scripted time, not a measurement.

| seed | cues | first reply wrong | shipped right | shipped wrong | left in English | calls, first replies / with retries |
|---|---|---|---|---|---|---|
| 1 | 180 | 41 (23%) | 173 | 5 | 2 | 24 / 33 |
| 2 | 180 | 43 (24%) | 167 | 7 | 6 | 24 / 34 |
| 3 | 180 | 47 (26%) | 168 | 4 | 8 | 24 / 34 |
| 4 | 180 | 45 (25%) | 168 | 7 | 5 | 24 / 33 |
| 5 | 180 | 46 (26%) | 169 | 3 | 8 | 24 / 34 |
| all | 900 | 222 (25%) | 845 | 26 | 29 | 120 / 168 |

Scripted latency over all seeds: 95 s for first replies only, 129 s with retries. Cues whose line breaks reflow moved: 1.

| fault in the output | times it occurred | rejected by the checks | share rejected | shipped anyway |
|---|---|---|---|---|
| drop | 41 | 41 | 100% | 0 |
| duplicate | 22 | 22 | 100% | 0 |
| merge | 15 | 15 | 100% | 0 |
| number | 41 | 41 | 100% | 0 |
| tag | 5 | 5 | 100% | 0 |
| long | 57 | 57 | 100% | 0 |
| english | 41 | 34 | 83% | 7 |
| commentary | 47 | 47 | 100% | 0 |
| wrong_noun | 20 | 1 | 5% | 19 |
| merged_away | 15 | 15 | 100% | 0 |
| truncated | 16 | 16 | 100% | 0 |

Outputs with no fault: 845, rejected by the checks: 0 (0%).

<!-- standin:end -->

### Live models

`python -m subtitle_translate.bench live --model NAME` sends `samples/demo.srt` through a local Ollama model three times. The file is 39 cues of narration I wrote (`samples/make_demo.py` makes it). "First reply rejected" counts cues, and the seed of each run is stored in the JSON. Server, GPU and model digests are in `results/exploratory/ollama-info.txt`.

<!-- live:start -->

Model `gemma3:latest`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 8 | 31 / 6 / 2 | 6 | 7 | 34 |
| 2 | 39 | 8 | 31 / 6 / 2 | 6 | 7 | 26 |
| 3 | 39 | 10 | 29 / 8 / 2 | 6 | 8 | 28 |

Why first replies were rejected, all runs: unchanged 15, tags 6, reading_speed 5.

Model `llama3.2:3b`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 2 | 37 / 0 / 2 | 6 | 7 | 25 |
| 2 | 39 | 4 | 35 / 4 / 0 | 10 | 6 | 18 |
| 3 | 39 | 9 | 30 / 0 / 9 | 8 | 9 | 27 |

Why first replies were rejected, all runs: model_error 7, line_length 3, reading_speed 3, length_ratio 1, numbers 1, tags 1.

Model `qwen3:4b-instruct-2507-q4_K_M`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 4 | 35 / 4 / 0 | 6 | 6 | 28 |
| 2 | 39 | 6 | 33 / 6 / 0 | 9 | 7 | 23 |
| 3 | 39 | 7 | 32 / 7 / 0 | 5 | 7 | 24 |

Why first replies were rejected, all runs: reading_speed 7, length_ratio 4, missing 3, duplicate 2, unchanged 2.

<!-- live:end -->

## Things that went wrong

- My first live run, with gemma3 before `reflow.py` existed (`results/exploratory/gemma3-before-reflow.report.json`), rejected 11 of 39 cues on the first reply. 8 had a line that was too long, and for 6 of them `line_length` was the only reason. A line break is a deterministic fix, so I wrote `reflow.py` instead of asking the model again. Not every one of the six was a good translation: cue 16 came back as "su un schermo", which no check can see.
- In these runs every gemma3 reply needed repair: `repaired_replies` equals `calls` in the run above and in all three runs of `results/live-gemma3_latest.json`. One raw reply, kept in `results/exploratory/gemma3-reply-start.txt`, starts with a json code fence. The replies of the other two models never needed repair.
- In llama3.2:3b run 3, the call for cues 33 to 39 came back from Ollama as HTTP 500, "prediction aborted, token repeat limit reached". Cues 28 and 31 had been rejected too. Eight of those nine cues then came back on the first retry as something that was not a JSON array of objects (`bad_reply`). On the last retry eight came back with tags around single words and one was missing from the reply, so all nine were left in English. The report first said only `model_error`; I replayed the call to read the server's reason, and the report now keeps it (`results/live-llama3.2_3b.json`).
- My first live tables (`results/exploratory/first-live-batch/live-gemma3_latest.md`) show "numbers 3" and "length_ratio 6" for gemma3. Both came from one bug: an unclosed `<i` matched the tag pattern up to the next `>` and hid the rest of the cue, digits included. The tag pattern now stops at the next `<`. At the same time I made the number check order-sensitive, added the dialogue-dash check, and stopped applying the length ratio to sources under 5 characters. The tables above were regenerated afterwards.
- I repeated the gemma3 command with the final code (`results/exploratory/repeat-gemma3/`) and got the same counts; only the wall seconds changed. The first batch (`results/exploratory/first-live-batch/`) used older checks, so it cannot be compared with the final one.

## What this does not show

- The stand-in's fault rates are mine and it does not model how a real model fails. I wrote the checks knowing which faults it makes, so rejecting nearly all of them shows that the code path works. It says nothing about how many mistakes a real model makes or whether these checks would catch them.
- A changed noun passes: 19 of the 20 wrong-noun cues in the stand-in table shipped. The English check only looks at cues of three or more words, so a short cue left in English passes: 7 of the 41 English replies shipped.
- Digit separators are ignored, so "1,200" and "1.200" match, and so does a wrong separator that leaves the same runs of digits.
- The data is synthetic. The stand-in builds its English from a short list of templates, and the live file is 39 cues I wrote, six of them timed at 17 characters per second against the limit of 20.
- The live results are one machine and three runs of one file per model, and I repeated only the gemma3 command once. The tables count cues the checks accepted or rejected. I did not grade the Italian, and a cue that passes can still be a poor translation.
- Wall seconds vary on this machine. The same llama3.2:3b command took 63 seconds for run 1 in the first batch and 25 in the final one (`results/exploratory/first-live-batch/live-llama3.2_3b.md`, `results/live-llama3.2_3b.md`).
- Retries cost calls: the last column of the stand-in table shows the calls for first replies only against all calls.

## Licence and history

MIT, see `LICENSE`. I rebuilt the commits from the finished tree, one part at a time in the order I built the parts, and ran the tests on each tree before committing it. Fixes and tests I added later, such as the server's error message in the report and the tests I wrote after breaking the code on copies, sit in the commit of the part they belong to. Commit dates are the date of the rebuild, not of the first writing.
