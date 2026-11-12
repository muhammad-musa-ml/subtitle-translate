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
