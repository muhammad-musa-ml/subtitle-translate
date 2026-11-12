import random
import unittest

from subtitle_translate.checks import Rules, strip_markup
from subtitle_translate.reflow import reflow

R = Rules()  # 2 lines of 42


class ReflowTests(unittest.TestCase):
    def test_text_that_fits_is_returned_as_it_is(self):
        for text in ("Short.", "x" * 42, "a b\nc d", "x" * 42 + "\n" + "y" * 42):
            self.assertEqual(reflow(text, R), text)

    def test_a_long_single_line_is_split_in_two_balanced_lines(self):
        out = reflow("Controlla ogni didascalia prima di pubblicare.", R)
        self.assertEqual(out, "Controlla ogni didascalia\nprima di pubblicare.")
        self.assertEqual(out.split(), "Controlla ogni didascalia prima di pubblicare.".split())

    def test_forty_three_characters_are_enough_to_need_a_break(self):
        text = "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd"  # 4 x 10 + 3 spaces = 43
        out = reflow(text, R)
        self.assertEqual(out, "aaaaaaaaaa bbbbbbbbbb\ncccccccccc dddddddddd")

    def test_existing_line_breaks_are_replaced_when_the_text_does_not_fit(self):
        out = reflow("x" * 30 + " " + "y" * 20 + "\nz", R)
        self.assertEqual(out, "x" * 30 + "\n" + "y" * 20 + " z")

    def test_tags_do_not_count_and_are_never_split(self):
        text = "<i>" + " ".join(["abcde"] * 8) + "</i>"   # 8 words of 5 + 7 spaces = 47 plain characters
        out = reflow(text, R)
        self.assertEqual([len(strip_markup(x)) for x in out.split("\n")], [23, 23])
        self.assertEqual(out.split(), text.split())
        self.assertTrue(out.startswith("<i>abcde") and out.endswith("abcde</i>"))

    def test_tag_width_is_not_counted_when_deciding_whether_text_fits(self):
        # The first line is 41 characters plain and 44 with the tag, so it fits.
        text = "<i>" + "x" * 20 + " " + "y" * 20 + "\n" + "z" * 5 + "</i>"
        self.assertEqual(reflow(text, R), text)

    def test_tag_width_is_not_counted_when_choosing_where_to_break(self):
        # Plain word widths 10 10 10 10 12: the best break leaves 32 and 23. If the tag on the
        # first word were counted, the break would move one word earlier and leave 21 and 34.
        words = ["<b>" + "a" * 10 + "</b>"] + ["b" * 10] * 3 + ["c" * 12]
        out = reflow(" ".join(words), R)
        self.assertEqual([len(strip_markup(x)) for x in out.split("\n")], [32, 23])

    def test_a_font_tag_with_attributes_is_not_split(self):
        text = '<font color="red">' + "x" * 30 + " " + "y" * 20 + "</font>"
        self.assertEqual(reflow(text, R), '<font color="red">' + "x" * 30 + "\n" + "y" * 20 + "</font>")

    def test_runs_of_spaces_and_tabs_become_single_spaces_when_the_text_is_re_broken(self):
        out = reflow("aaaaaaaaaa   bbbbbbbbbb\tcccccccccc dddddddddd", R)
        self.assertEqual(out, "aaaaaaaaaa bbbbbbbbbb\ncccccccccc dddddddddd")

    def test_three_short_lines_are_joined_into_one(self):
        self.assertEqual(reflow("one\ntwo\nthree", R), "one two three")

    def test_a_tag_with_a_space_inside_stays_whole(self):
        text = '<font color="red">' + " ".join(["abcde"] * 8) + "</font>"
        out = reflow(text, R)
        self.assertEqual(out.count('<font color="red">'), 1)
        self.assertNotIn('<font\n', out)
        self.assertTrue(out.split("\n")[0].startswith('<font color="red">abcde'))

    def test_dialogue_dashes_are_left_alone(self):
        text = "- " + "x" * 30 + " " + "y" * 20 + "\n- Yes."
        self.assertEqual(reflow(text, R), text)

    def test_a_blank_line_is_left_alone(self):
        text = "x" * 30 + " " + "y" * 20 + "\n\nz"
        self.assertEqual(reflow(text, R), text)

    def test_text_that_cannot_fit_is_left_alone(self):
        too_long = " ".join(["abcdefghi"] * 10)          # 99 characters, two lines hold 84
        self.assertEqual(reflow(too_long, R), too_long)
        self.assertEqual(reflow("x" * 43, R), "x" * 43)    # a word wider than a line

    def test_more_lines_when_the_rules_allow_them(self):
        text = " ".join(["abcdefghi"] * 10)
        out = reflow(text, Rules(max_lines=3))
        self.assertEqual(len(out.split("\n")), 3)
        self.assertTrue(all(len(x) <= 42 for x in out.split("\n")))

    def test_only_line_breaks_change(self):
        rng = random.Random(1)
        words = ["il", "player", "richiede", "<i>sempre</i>", "{\\an8}", "dodici", "secondi", "a", "casa"]
        for _ in range(300):
            text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 14)))
            out = reflow(text, R)
            self.assertEqual(out.split(), text.split())
            self.assertLessEqual(len(out.split("\n")), 2 if out != text else len(text.split("\n")))
            if out != text:
                self.assertTrue(all(len(strip_markup(x)) <= 42 for x in out.split("\n")))


if __name__ == "__main__":
    unittest.main()
