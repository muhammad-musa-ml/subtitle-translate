Model `gemma3:latest`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 9 | 30 / 8 / 1 | 6 | 8 | 28.2 |
| 2 | 39 | 8 | 31 / 5 / 3 | 7 | 7 | 26.5 |
| 3 | 39 | 10 | 29 / 9 / 1 | 6 | 8 | 27.9 |

Why first replies were rejected, all runs: unchanged 15, length_ratio 6, reading_speed 6, tags 6, numbers 3.
