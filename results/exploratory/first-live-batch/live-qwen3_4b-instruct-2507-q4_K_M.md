Model `qwen3:4b-instruct-2507-q4_K_M`, English to Italian, `demo.srt`, 3 runs (sampling seed = run number, temperature 0.3).

| run | cues | first reply rejected | shipped first try / after retry / left in English | line breaks moved | calls | wall seconds |
|---|---|---|---|---|---|---|
| 1 | 39 | 4 | 35 / 4 / 0 | 6 | 6 | 28.1 |
| 2 | 39 | 6 | 33 / 6 / 0 | 9 | 7 | 23.5 |
| 3 | 39 | 7 | 32 / 7 / 0 | 5 | 7 | 24.2 |

Why first replies were rejected, all runs: reading_speed 7, length_ratio 4, missing 3, duplicate 2, unchanged 2.
