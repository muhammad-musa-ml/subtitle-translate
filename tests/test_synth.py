import unittest

from subtitle_translate import synth
from subtitle_translate.checks import check_cue


class SynthTests(unittest.TestCase):
    def test_same_seed_same_file(self):
        self.assertEqual(synth.generate(5, 30), synth.generate(5, 30))

    def test_different_seeds_differ(self):
        self.assertNotEqual(synth.generate(5, 30)[0], synth.generate(6, 30)[0])

    def test_cues_are_numbered_in_order_and_do_not_overlap(self):
        cues, _ = synth.generate(3, 50)
        self.assertEqual([c.index for c in cues], list(range(1, 51)))
        for a, b in zip(cues, cues[1:]):
            self.assertGreaterEqual(b.start_ms, a.end_ms)
        self.assertTrue(all(c.end_ms > c.start_ms for c in cues))

    def test_every_cue_has_a_reference(self):
        cues, ref = synth.generate(4, 50)
        self.assertTrue(all(c.text in ref for c in cues))

    def test_reference_is_not_the_source(self):
        cues, ref = synth.generate(4, 50)
        self.assertTrue(all(ref[c.text] != c.text for c in cues))

    def test_correct_translations_pass_every_check(self):
        # The false-positive control: the checks must accept the right answer.
        bad = []
        for seed in range(1, 101):
            cues, ref = synth.generate(seed, 40)
            for c in cues:
                codes = check_cue(c, ref[c.text])
                if codes:
                    bad.append((seed, c.index, c.text, ref[c.text], codes))
        self.assertEqual(bad, [])

    def test_no_template_gives_one_english_text_two_italian_texts(self):
        # generate() keeps one reference per English text, so a conflict here would make a right answer wrong.
        seen = {}
        for en_t, it_t in synth.TEMPLATES:
            for noun in synth.NOUNS:
                for n_en, n_it in (("7", "7"), ("2.4", "2,4"), ("1,200", "1.200")):
                    en = en_t.format(the="the " + noun[0], The="The " + noun[0], n=n_en, m="5")
                    it = it_t.format(il=noun[1], Il=noun[2], n=n_it, m="5")
                    self.assertEqual(seen.setdefault(en, it), it, en)

    def test_templates_cover_numbers_tags_music_and_two_line_cues(self):
        cues, _ = synth.generate(1, 400)
        texts = [c.text for c in cues]
        self.assertTrue(any("<i>" in t for t in texts))
        self.assertTrue(any("[MUSIC]" in t for t in texts))
        self.assertTrue(any("\n" in t for t in texts))
        self.assertTrue(any("," in t and any(ch.isdigit() for ch in t) for t in texts))


if __name__ == "__main__":
    unittest.main()
