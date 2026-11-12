import os
import subprocess
import sys
import tempfile
import unittest

from subtitle_translate import srt
from subtitle_translate.checks import strip_markup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "samples", "demo.srt")


class SampleTests(unittest.TestCase):
    def test_the_sample_is_what_make_demo_writes(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "demo.srt")
            subprocess.run([sys.executable, "-X", "utf8", os.path.join(ROOT, "samples", "make_demo.py"), out], check=True)
            with open(out, "rb") as made, open(DEMO, "rb") as stored:
                self.assertEqual(made.read(), stored.read())

    def test_the_sample_parses_and_its_timing_is_tight_in_six_places(self):
        with open(DEMO, encoding="utf-8") as fh:
            cues = srt.parse(fh.read())
        self.assertEqual(len(cues), 39)
        self.assertEqual([c.index for c in cues], list(range(1, 40)))
        tight = [c.index for c in cues if len(strip_markup(c.text).replace("\n", " ")) / c.duration_s > 15.5]
        self.assertEqual(tight, [14, 17, 19, 25, 29, 31])


if __name__ == "__main__":
    unittest.main()
