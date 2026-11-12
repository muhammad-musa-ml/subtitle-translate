Model `llama3.2:3b`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 2 | 37 / 0 / 2 | 6 | 7 | 25 |
| 2 | 39 | 4 | 35 / 4 / 0 | 10 | 6 | 18 |
| 3 | 39 | 9 | 30 / 0 / 9 | 8 | 9 | 27 |

Why first replies were rejected, all runs: model_error 7, line_length 3, reading_speed 3, length_ratio 1, numbers 1, tags 1.
