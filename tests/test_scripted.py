import json
import unittest

from subtitle_translate import synth
from subtitle_translate.model import Request, parse_reply
from subtitle_translate.scripted import Rates, ScriptedModel, _wrong_noun

NONE = dict.fromkeys(
    ["drop", "duplicate", "merge", "number", "tag", "long", "english", "commentary", "wrong_noun",
     "fenced", "truncated", "stubborn"], 0.0)


def rates(**kw):
    return Rates(**dict(NONE, **kw))


REF = {
    "It takes 12 seconds.": "Richiede 12 secondi.",
    "<i>Wait for the player.</i>": "<i>Aspetta il player.</i>",
    "[MUSIC]": "[MUSICA]",
}
CUES = [(1, "It takes 12 seconds."), (2, "<i>Wait for the player.</i>"), (3, "[MUSIC]")]


def ask(model, cues=CUES):
    reply = model.translate(Request("Italian", cues))
    items, _ = parse_reply(reply.text)
    return reply, items


class ScriptedModelTests(unittest.TestCase):
    def test_without_faults_it_returns_the_reference_and_logs_none(self):
        m = ScriptedModel(REF, 1, rates())
        _, items = ask(m)
        self.assertEqual([(i["id"], i["text"]) for i in items], [(1, "Richiede 12 secondi."),
                         (2, "<i>Aspetta il player.</i>"), (3, "[MUSICA]")])
        self.assertTrue(all(e["fault"] is None for e in m.log))
        self.assertEqual([e["id"] for e in m.log], [1, 2, 3])

    def test_same_seed_same_replies_and_other_seed_differs(self):
        cues, ref = synth.generate(9, 40)
        req = Request("Italian", [(c.index, c.text) for c in cues[:8]])
        a = ScriptedModel(ref, 1, Rates(drop=0.3, number=0.3)).translate(req)
        b = ScriptedModel(ref, 1, Rates(drop=0.3, number=0.3)).translate(req)
        c = ScriptedModel(ref, 2, Rates(drop=0.3, number=0.3)).translate(req)
        self.assertEqual(a, b)
        self.assertNotEqual(a.text, c.text)

    def test_number_fault_changes_the_digits_and_is_logged(self):
        m = ScriptedModel(REF, 1, rates(number=1.0))
        _, items = ask(m)
        self.assertEqual(items[0]["text"], "Richiede 13 secondi.")
        self.assertEqual(m.log[0]["fault"], "number")

    def test_a_fault_that_cannot_apply_is_not_logged(self):
        m = ScriptedModel(REF, 1, rates(number=1.0))
        _, items = ask(m)
        self.assertEqual(items[2]["text"], "[MUSICA]")
        self.assertIsNone(m.log[2]["fault"])
        m2 = ScriptedModel(REF, 1, rates(tag=1.0))
        _, items2 = ask(m2)
        self.assertEqual(items2[0]["text"], "Richiede 12 secondi.")
        self.assertIsNone(m2.log[0]["fault"])
        self.assertEqual((items2[1]["text"], m2.log[1]["fault"]), ("Aspetta il player.", "tag"))

    def test_drop_omits_the_cue(self):
        m = ScriptedModel(REF, 1, rates(drop=1.0))
        _, items = ask(m)
        self.assertEqual(items, [])
        self.assertEqual({e["fault"] for e in m.log}, {"drop"})

    def test_duplicate_repeats_the_id(self):
        m = ScriptedModel(REF, 1, rates(duplicate=1.0))
        _, items = ask(m, CUES[:1])
        self.assertEqual([i["id"] for i in items], [1, 1])

    def test_merge_joins_the_next_cue_and_drops_it(self):
        m = ScriptedModel(REF, 1, rates(merge=1.0))
        _, items = ask(m, CUES[:2])
        self.assertEqual([i["id"] for i in items], [1])
        self.assertEqual(items[0]["text"], "Richiede 12 secondi.\n<i>Aspetta il player.</i>")
        self.assertEqual([e["fault"] for e in m.log], ["merge", "merged_away"])

    def test_merge_on_the_last_cue_does_nothing(self):
        m = ScriptedModel(REF, 1, rates(merge=1.0))
        _, items = ask(m, CUES[2:])
        self.assertEqual(items[0]["text"], "[MUSICA]")
        self.assertIsNone(m.log[0]["fault"])

    def test_long_english_and_commentary(self):
        for fault, expect in (("long", "Richiede 12 secondi. Richiede 12 secondi."),
                              ("english", "It takes 12 seconds."),
                              ("commentary", "Ecco la traduzione: Richiede 12 secondi.")):
            m = ScriptedModel(REF, 1, rates(**{fault: 1.0}))
            _, items = ask(m, CUES[:1])
            self.assertEqual(items[0]["text"], expect)
            self.assertEqual(m.log[0]["fault"], fault)

    def test_wrong_noun_swaps_the_noun_only(self):
        self.assertEqual(_wrong_noun("Il player richiede 5 secondi."), "L'editor richiede 5 secondi.")
        self.assertEqual(_wrong_noun("Apri prima l'anteprima."), "Apri prima il render.")
        self.assertIsNone(_wrong_noun("Passaggio 3 di 5."))

    def test_fenced_reply_is_readable_and_logged(self):
        m = ScriptedModel(REF, 1, rates(fenced=1.0))
        reply, items = ask(m)
        self.assertTrue(reply.text.startswith("```json"))
        self.assertEqual(len(items), 3)
        self.assertEqual({e["batch_fault"] for e in m.log}, {"fenced"})
        self.assertTrue(all(e["fault"] is None for e in m.log))

    def test_truncated_reply_is_unreadable_and_logged(self):
        m = ScriptedModel(REF, 1, rates(truncated=1.0))
        reply, items = ask(m)
        self.assertIsNone(items)
        self.assertEqual({e["fault"] for e in m.log}, {"truncated"})

    def test_stubborn_cues_repeat_the_same_fault(self):
        # This cue has a digit and a noun, so every stubborn fault can be applied to it.
        ref = {"The player takes 12 seconds.": "Il player richiede 12 secondi."}
        cue = [(1, "The player takes 12 seconds.")]
        m = ScriptedModel(ref, 1, rates(stubborn=1.0))
        ask(m, cue)
        ask(m, cue)
        ask(m, cue)
        kinds = [e["fault"] for e in m.log if e["id"] == 1]
        self.assertEqual(len(set(kinds)), 1)
        self.assertIsNotNone(kinds[0])
        self.assertEqual([e["attempt"] for e in m.log], [1, 2, 3])

    def test_attempts_are_counted_per_cue_across_calls(self):
        m = ScriptedModel(REF, 1, rates())
        ask(m)
        ask(m, CUES[1:2])
        self.assertEqual([(e["id"], e["attempt"]) for e in m.log], [(1, 1), (2, 1), (3, 1), (2, 2)])

    def test_latency_is_scripted_and_grows_with_the_batch(self):
        m = ScriptedModel(REF, 1, rates())
        one = m.translate(Request("Italian", CUES[:1])).latency_s
        fifty = m.translate(Request("Italian", [(i, "[MUSIC]") for i in range(1, 51)])).latency_s
        self.assertTrue(0.35 + 0.045 <= one <= 0.35 + 0.045 + 0.2, one)
        self.assertTrue(0.35 + 0.045 * 50 <= fifty <= 0.35 + 0.045 * 50 + 0.2, fifty)

    def test_reply_is_json_with_integer_ids(self):
        m = ScriptedModel(REF, 1, rates())
        reply = m.translate(Request("Italian", CUES))
        self.assertTrue(all(type(i["id"]) is int for i in json.loads(reply.text)))


if __name__ == "__main__":
    unittest.main()
