import unittest

from subtitle_translate.checks import (ENGLISH_STOPWORDS, Rules, check_cue, dialogue_lines, digit_runs, markup,
                                        strip_markup)
from subtitle_translate.srt import Cue


def cue(text, ms=3000):
    return Cue(1, 0, ms, text)


class HelperTests(unittest.TestCase):
    def test_strip_markup_removes_tags_and_override_codes(self):
        self.assertEqual(strip_markup("<i>Hi</i> {\\an8}there"), "Hi there")

    def test_markup_keeps_order(self):
        self.assertEqual(markup("<b>a</b><i>b</i>"), ["<b>", "</b>", "<i>", "</i>"])

    def test_digit_runs_ignore_separators_and_markup_and_keep_their_order(self):
        self.assertEqual(digit_runs("1,200 and 2.5 <font size=3>x</font>"), ["1", "200", "2", "5"])

    def test_an_unclosed_tag_does_not_hide_the_text_after_it(self):
        self.assertEqual(strip_markup("<i We keep 30 days.</i>"), "<i We keep 30 days.")
        self.assertEqual(digit_runs("<i We keep 30 days.</i>"), ["30"])
        self.assertEqual(strip_markup("{an8 We keep 30 days.{b}"), "{an8 We keep 30 days.")

    def test_dialogue_lines_counts_dashes_outside_tags(self):
        self.assertEqual(dialogue_lines("- a\n- b"), 2)
        self.assertEqual(dialogue_lines("<i>- a</i>\nb"), 1)
        self.assertEqual(dialogue_lines("a - b"), 0)


class CheckTests(unittest.TestCase):
    def codes(self, source, out, **kw):
        c = source if isinstance(source, Cue) else cue(source)
        return check_cue(c, out, **kw)

    def test_a_clean_translation_has_no_codes(self):
        self.assertEqual(self.codes("We keep the folder for 30 days.", "Conserviamo la cartella per 30 giorni."), [])

    def test_empty(self):
        self.assertEqual(self.codes("Hello there", ""), ["empty"])
        self.assertEqual(self.codes("Hello there", "  \n "), ["empty"])

    def test_structure_blank_line_and_arrow(self):
        self.assertIn("structure", self.codes("Hello there my friend", "Ciao\n\namico"))
        self.assertIn("structure", self.codes("Hello there my friend", "Ciao --> amico"))
        self.assertNotIn("structure", self.codes("Hello there my friend", "Ciao\namico"))

    def test_lines(self):
        self.assertIn("lines", self.codes("Hello there my friend", "a\nb\nc"))
        self.assertNotIn("lines", self.codes("Hello there my friend", "a\nb"))
        self.assertNotIn("lines", self.codes("Hello there my friend", "a\nb\nc", rules=Rules(max_lines=3)))

    def test_line_length_boundary_and_markup(self):
        self.assertNotIn("line_length", self.codes("Hello there my friend", "x" * 42, rules=Rules(max_cps=99)))
        self.assertIn("line_length", self.codes("Hello there my friend", "x" * 43, rules=Rules(max_cps=99)))
        tagged = "<i>" + "x" * 42 + "</i>"
        self.assertNotIn("line_length", self.codes("<i>Hello there my friend</i>", tagged, rules=Rules(max_cps=99)))
        second_line_long = "ok\n" + "x" * 43
        self.assertIn("line_length", self.codes("Hello there my friend", second_line_long, rules=Rules(max_cps=99)))

    def test_reading_speed_boundary(self):
        one_second = cue("Hello there my friend", ms=1000)
        self.assertNotIn("reading_speed", check_cue(one_second, "x" * 20))
        self.assertIn("reading_speed", check_cue(one_second, "x" * 21))

    def test_reading_speed_counts_the_line_break_as_one_character(self):
        one_second = cue("Hello there my friend", ms=1000)
        self.assertNotIn("reading_speed", check_cue(one_second, "x" * 9 + "\n" + "y" * 10))
        self.assertIn("reading_speed", check_cue(one_second, "x" * 10 + "\n" + "y" * 10))

    def test_numbers(self):
        self.assertIn("numbers", self.codes("It takes 12 seconds", "Richiede 13 secondi"))
        self.assertIn("numbers", self.codes("It takes 12 seconds", "Richiede dodici secondi"))
        self.assertIn("numbers", self.codes("It takes 12 seconds", "Richiede 12 e 12 secondi"))
        self.assertEqual(self.codes("It costs 1,200 dollars", "Costa 1.200 dollari"), [])
        self.assertEqual(self.codes("It takes 2.5 seconds", "Richiede 2,5 secondi"), [])

    def test_numbers_must_come_in_the_same_order(self):
        self.assertIn("numbers", self.codes("From 5 to 10 people.", "Da 10 a 5 persone."))
        self.assertIn("numbers", self.codes("Version 2.5", "versione 5,2"))
        self.assertEqual(self.codes("From 5 to 10 people.", "Da 5 a 10 persone."), [])

    def test_an_unclosed_tag_is_a_tags_problem_and_nothing_else(self):
        src = "<i>We keep a copy for 30 days.</i>"
        self.assertEqual(self.codes(src, "<i Conserviamo una copia per 30 giorni.</i>"), ["tags"])

    def test_dialogue_dashes(self):
        src = "- Everyone on the team?\n- Only the 12 people."
        self.assertIn("dialogue", self.codes(src, "Tutti nel team? Solo le 12 persone."))
        self.assertIn("dialogue", self.codes(src, "- Tutti nel team?\nSolo le 12 persone."))
        self.assertEqual(self.codes(src, "- Tutti nel team?\n- Solo le 12 persone."), [])
        self.assertEqual(self.codes("<i>- Hello there my friend</i>", "<i>- Ciao a te amico</i>"), [])
        self.assertIn("dialogue", self.codes("Hello there my friend", "- Ciao a te amico"))

    def test_tags(self):
        src = "<i>Wait for the player</i>"
        self.assertIn("tags", self.codes(src, "Aspetta il player"))
        self.assertIn("tags", self.codes(src, "<i>Aspetta il player"))
        self.assertIn("tags", self.codes(src, "</i>Aspetta il player<i>"))
        self.assertIn("tags", self.codes("Wait for the player", "<b>Aspetta il player</b>"))
        self.assertEqual(self.codes(src, "<i>Aspetta il player</i>"), [])
        self.assertEqual(self.codes("{\\an8}Wait for the player", "{\\an8}Aspetta il player"), [])

    def test_unchanged(self):
        src = "We keep the project safe"
        self.assertIn("unchanged", self.codes(src, src))
        self.assertIn("unchanged", self.codes(src, src.upper()))
        self.assertNotIn("unchanged", self.codes(src, src, target_is_english=True))
        self.assertNotIn("unchanged", self.codes("OK, go on.", "OK, go on."))

    def test_unchanged_needs_twelve_letters_and_three_words(self):
        self.assertNotIn("unchanged", self.codes("Hello big cat", "Hello big cat"))      # 11 letters
        self.assertIn("unchanged", self.codes("Hello big cats", "Hello big cats"))       # 12 letters
        self.assertIn("unchanged", self.codes("Keep the safe project", "Keep the safe project"))
        self.assertEqual(self.codes("It is", "It is"), [])                                # two words are not judged

    def test_the_stopword_list_leaves_out_words_of_the_target_languages(self):
        self.assertNotIn("for", ENGLISH_STOPWORDS)    # "for" is Portuguese

    def test_english_left(self):
        src = "Press the button, then look"
        self.assertIn("english_left", self.codes(src, "Press the button to see the result"))
        self.assertNotIn("english_left", self.codes(src, "Premi il pulsante, poi guarda"))
        self.assertNotIn("english_left", self.codes(src, "Premi the pulsante poi guarda"))  # 1 of 5 words
        self.assertIn("english_left", self.codes(src, "Premi the and pulsante"))  # 2 of 4 words
        self.assertNotIn("english_left", self.codes(src, "Press the button to see the result", target_is_english=True))

    def test_commentary(self):
        src = "Open the editor first"
        for text in ("Ecco la traduzione: Apri prima l'editor", "Traduzione: Apri prima l'editor",
                     "Sure! Apri prima l'editor", "Certainly, apri prima l'editor", "Note: apri l'editor",
                     "```\nApri prima l'editor\n```"):
            self.assertIn("commentary", self.codes(src, text), text)
        for text in ("Ecco l'editor, aprilo prima", "Certo, apri prima l'editor", "Apri prima l'editor"):
            self.assertNotIn("commentary", self.codes(src, text), text)

    def test_length_ratio(self):
        src = "x" * 100
        self.assertIn("length_ratio", self.codes(src, "y" * 49))
        self.assertNotIn("length_ratio", self.codes(src, "y" * 50))
        self.assertNotIn("length_ratio", self.codes(src, "y" * 200))
        self.assertIn("length_ratio", self.codes(src, "y" * 201))

    def test_length_ratio_is_not_judged_for_very_short_sources(self):
        self.assertNotIn("length_ratio", self.codes("Hi", "Salve"))                      # 2 characters
        self.assertNotIn("length_ratio", self.codes("Yes.", "Sì, certo!"))               # 4 characters, ratio 2.5
        self.assertIn("length_ratio", self.codes("Okay.", "D'accordo, va bene."))        # 5 characters
        self.assertIn("length_ratio", self.codes("Hi", "Salve", rules=Rules(ratio_min_source_chars=1)))

    def test_a_wrong_word_passes(self):
        # Stated limit: nothing here can see a changed noun.
        self.assertEqual(self.codes("We keep the folder for 30 days.", "Conserviamo il progetto per 30 giorni."), [])


if __name__ == "__main__":
    unittest.main()
