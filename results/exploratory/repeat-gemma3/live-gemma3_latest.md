Model `gemma3:latest`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 8 | 31 / 6 / 2 | 6 | 7 | 35 |
| 2 | 39 | 8 | 31 / 6 / 2 | 6 | 7 | 26 |
| 3 | 39 | 10 | 29 / 8 / 2 | 6 | 8 | 28 |

Why first replies were rejected, all runs: unchanged 15, tags 6, reading_speed 5.
