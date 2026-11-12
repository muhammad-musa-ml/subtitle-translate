import unittest

from subtitle_translate import srt

SAMPLE = (
    "1\n00:00:01,000 --> 00:00:02,500\nHello\n\n"
    "2\n00:00:03,000 --> 00:00:04,000\n<i>Two</i>\nlines\n"
)


class TimestampTests(unittest.TestCase):
    def test_round_trip(self):
        for ms in (0, 1, 999, 1000, 59_999, 3_599_999, 3_600_000, 86_399_999):
            self.assertEqual(srt.ts_to_ms(srt.ms_to_ts(ms)), ms)

    def test_format(self):
        self.assertEqual(srt.ms_to_ts(3_723_004), "01:02:03,004")
        self.assertEqual(srt.ms_to_ts(0), "00:00:00,000")

    def test_dot_separator_is_read(self):
        self.assertEqual(srt.ts_to_ms("00:00:01.500"), 1500)

    def test_rejects_bad_timestamps(self):
        for bad in ("00:61:00,000", "00:00:60,000", "1:2:3", "00:00:01", "aa:bb:cc,ddd", ""):
            with self.assertRaises(ValueError, msg=bad):
                srt.ts_to_ms(bad)


class ParseTests(unittest.TestCase):
    def test_basic(self):
        cues = srt.parse(SAMPLE)
        self.assertEqual([c.index for c in cues], [1, 2])
        self.assertEqual((cues[0].start_ms, cues[0].end_ms, cues[0].text), (1000, 2500, "Hello"))
        self.assertEqual(cues[1].text, "<i>Two</i>\nlines")
        self.assertAlmostEqual(cues[0].duration_s, 1.5)

    def test_format_round_trip(self):
        self.assertEqual(srt.format(srt.parse(SAMPLE)), SAMPLE)

    def test_crlf_and_bom(self):
        raw = "﻿" + SAMPLE.replace("\n", "\r\n")
        self.assertEqual(srt.parse(raw), srt.parse(SAMPLE))

    def test_last_cue_without_trailing_newline(self):
        self.assertEqual(len(srt.parse(SAMPLE.rstrip("\n"))), 2)

    def test_position_settings_after_the_end_time_are_ignored(self):
        cues = srt.parse("1\n00:00:01,000 --> 00:00:02,000 X1:100 X2:200\nHi\n")
        self.assertEqual(cues[0].end_ms, 2000)

    def test_extra_blank_lines_between_cues(self):
        self.assertEqual(len(srt.parse("\n\n" + SAMPLE.replace("\n\n", "\n\n\n\n"))), 2)

    def test_empty_file_has_no_cues(self):
        self.assertEqual(srt.parse(""), [])

    def test_errors_name_the_line(self):
        cases = {
            "x\n00:00:01,000 --> 00:00:02,000\nHi\n": "line 1",
            "1\nnot a timing\nHi\n": "line 2: expected a timing line after cue 1",
            "1\n00:00:02,000 --> 00:00:01,000\nHi\n": "line 2",
            "1\n00:00:01,000 -->\nHi\n": "line 2: no end time for cue 1",
            "1\n00:00:01,000 --> 00:00:02,000\nHi\n\n1\n00:00:03,000 --> 00:00:04,000\nHo\n": "appears twice",
            "1\n00:00:01,000 --> 00:00:99,000\nHi\n": "line 2",
            "1\n00:00:02,000 --> 00:00:02,000\nHi\n": "line 2: cue 1 ends before it starts",
            "1": "line 2: expected a timing line after cue 1",
        }
        for text, needle in cases.items():
            with self.assertRaises(srt.SrtError, msg=text) as ctx:
                srt.parse(text)
            self.assertIn(needle, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
