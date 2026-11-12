import json
import unittest

from subtitle_translate import pipeline, synth
from subtitle_translate.checks import check_cue
from subtitle_translate.model import ModelError, Reply
from subtitle_translate.scripted import Rates, ScriptedModel
from subtitle_translate.srt import Cue


class Scripted:
    """Returns the reference translation; `script[n]` rewrites what call n returns."""

    def __init__(self, reference, script=None):
        self.reference = reference
        self.script = script or {}
        self.requests = []

    def translate(self, req):
        self.requests.append(req)
        items = [{"id": i, "text": self.reference[t]} for i, t in req.cues]
        change = self.script.get(len(self.requests))
        if change is not None:
            items = change(items)
        if isinstance(items, Exception):
            raise items
        raw = items if isinstance(items, str) else json.dumps(items, ensure_ascii=False)
        return Reply(raw, 1.0)


def corrupt(index, **fields):
    def apply(items):
        return [dict(x, **fields) if x["id"] == index else x for x in items]
    return apply


def setup(n=10, seed=2):
    cues, ref = synth.generate(seed, n)
    return cues, ref


class CleanRunTests(unittest.TestCase):
    def test_every_cue_ships_on_the_first_try(self):
        cues, ref = setup(10)
        model = Scripted(ref)
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual([r.status for r in res.cues], ["ok"] * 10)
        self.assertEqual([r.text for r in res.cues], [ref[c.text] for c in cues])
        self.assertEqual(res.calls, 2)
        self.assertEqual(res.latency_s, 2.0)
        self.assertEqual(res.round_calls, [2])
        self.assertTrue(all(r.attempts == 1 and r.first_codes == [] for r in res.cues))

    def test_batches_follow_batch_size(self):
        cues, ref = setup(20)
        model = Scripted(ref)
        pipeline.translate(cues, model, "Italian", batch_size=8)
        self.assertEqual([len(r.cues) for r in model.requests], [8, 8, 4])

    def test_batch_size_sets_the_cues_per_request(self):
        cues, ref = setup(10)
        model = Scripted(ref)
        pipeline.translate(cues, model, "Italian", batch_size=3)
        self.assertEqual([len(r.cues) for r in model.requests], [3, 3, 3, 1])

    def test_translated_cues_keep_numbers_and_times(self):
        cues, ref = setup(10)
        res = pipeline.translate(cues, Scripted(ref), "Italian")
        out = res.translated(cues)
        self.assertEqual([(c.index, c.start_ms, c.end_ms) for c in out], [(c.index, c.start_ms, c.end_ms) for c in cues])
        self.assertEqual([c.text for c in out], [ref[c.text] for c in cues])

    def test_no_cues_no_calls(self):
        res = pipeline.translate([], Scripted({}), "Italian")
        self.assertEqual((res.cues, res.calls), ([], 0))

    def test_bad_settings_are_refused(self):
        with self.assertRaises(ValueError):
            pipeline.translate([], Scripted({}), "Italian", batch_size=0)
        with self.assertRaises(ValueError):
            pipeline.translate([], Scripted({}), "Italian", max_retries=-1)

    def test_text_is_trimmed(self):
        cues, ref = setup(3)
        model = Scripted(ref, {1: corrupt(1, text="  " + ref[cues[0].text] + "\n ")})
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual(res.cues[0].text, ref[cues[0].text])
        self.assertEqual(res.cues[0].status, "ok")


class RetryTests(unittest.TestCase):
    def test_a_rejected_cue_is_asked_again_alone_with_the_reason(self):
        cues, ref = setup(10)
        bad = ref[cues[2].text] + " tre"
        model = Scripted(ref, {1: corrupt(3, text="Ecco la traduzione: " + bad)})
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual(len(model.requests), 3)
        retry = model.requests[2]
        self.assertEqual([i for i, _ in retry.cues], [3])
        self.assertIn("commentary", retry.feedback[3])
        r = res.cues[2]
        self.assertEqual((r.status, r.attempts, r.text), ("retried", 2, ref[cues[2].text]))
        self.assertIn("commentary", r.first_codes)
        self.assertEqual(r.accepted_call, 3)
        self.assertEqual(res.round_calls, [2, 1])

    def test_first_requests_carry_no_feedback(self):
        cues, ref = setup(10)
        model = Scripted(ref)
        pipeline.translate(cues, model, "Italian")
        self.assertTrue(all(r.feedback == {} for r in model.requests))

    def test_a_cue_that_never_passes_falls_back_to_the_source(self):
        cues, ref = setup(5)
        always = {n: corrupt(2, text="") for n in range(1, 10)}
        model = Scripted(ref, always)
        res = pipeline.translate(cues, model, "Italian", max_retries=2)
        r = res.cues[1]
        self.assertEqual((r.status, r.attempts, r.text), ("fallback", 3, cues[1].text))
        self.assertIsNone(r.accepted_call)
        self.assertEqual(res.calls, 3)

    def test_zero_retries_falls_back_at_once(self):
        cues, ref = setup(5)
        model = Scripted(ref, {1: corrupt(2, text="")})
        res = pipeline.translate(cues, model, "Italian", max_retries=0)
        self.assertEqual((res.cues[1].status, res.cues[1].first_codes, res.calls), ("fallback", ["empty"], 1))

    def test_retry_count_is_exact(self):
        cues, ref = setup(5)
        model = Scripted(ref, {n: corrupt(2, text="") for n in range(1, 20)})
        pipeline.translate(cues, model, "Italian", max_retries=4)
        self.assertEqual(len(model.requests), 5)

    def test_retries_are_batched_too(self):
        cues, ref = setup(20)
        script = {1: lambda items: [dict(x, text="") for x in items]}
        model = Scripted(ref, script)
        res = pipeline.translate(cues, model, "Italian", batch_size=8, max_retries=1)
        sizes = [len(r.cues) for r in model.requests]
        self.assertEqual(sizes, [8, 8, 4, 8])  # the first batch failed; the rest of round one was fine
        self.assertEqual(res.calls, 4)
        self.assertEqual([r.status for r in res.cues[:8]], ["retried"] * 8)


class ReplyShapeTests(unittest.TestCase):
    def codes_for(self, change, which=0):
        cues, ref = setup(4)
        model = Scripted(ref, {1: change})
        res = pipeline.translate(cues, model, "Italian", max_retries=0)
        return res.cues[which].first_codes, res

    def test_missing_id(self):
        codes, _ = self.codes_for(lambda items: [x for x in items if x["id"] != 1])
        self.assertEqual(codes, ["missing"])

    def test_duplicated_id_is_rejected_even_if_both_copies_are_right(self):
        codes, _ = self.codes_for(lambda items: items + [items[0]])
        self.assertEqual(codes, ["duplicate"])

    def test_extra_ids_are_ignored(self):
        codes, res = self.codes_for(lambda items: items + [{"id": 999, "text": "boo"}], which=1)
        self.assertEqual(codes, [])
        self.assertEqual(res.cues[1].status, "ok")

    def test_ids_must_be_integers(self):
        for wrong in (True, "1", 1.0, None):
            codes, _ = self.codes_for(lambda items, w=wrong: [dict(items[0], id=w)] + items[1:])
            self.assertEqual(codes, ["missing"], repr(wrong))

    def test_text_must_be_a_string(self):
        for wrong in (None, 5, ["a"]):
            codes, _ = self.codes_for(corrupt(1, text=wrong))
            self.assertEqual(codes, ["missing"], repr(wrong))

    def test_unreadable_reply_rejects_the_whole_batch(self):
        cues, ref = setup(10)
        model = Scripted(ref, {1: lambda items: '[{"id": 1, "text": "cut'})
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual([r.first_codes for r in res.cues[:8]], [["bad_reply"]] * 8)
        self.assertEqual([r.first_codes for r in res.cues[8:]], [[], []])
        self.assertEqual([r.status for r in res.cues[:8]], ["retried"] * 8)

    def test_fenced_reply_is_accepted_and_counted(self):
        cues, ref = setup(4)
        model = Scripted(ref, {1: lambda items: "```json\n" + json.dumps(items) + "\n```"})
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual([r.status for r in res.cues], ["ok"] * 4)
        self.assertEqual(res.repaired_replies, 1)

    def test_a_failed_call_is_retried_and_adds_no_latency(self):
        cues, ref = setup(4)
        model = Scripted(ref, {1: lambda items: ModelError("down")})
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual([r.first_codes for r in res.cues], [["model_error"]] * 4)
        self.assertEqual([r.status for r in res.cues], ["retried"] * 4)
        self.assertEqual((res.calls, res.latency_s), (2, 1.0))

    def test_a_failed_call_keeps_the_error_text_in_the_attempt_log(self):
        cues, ref = setup(4)
        model = Scripted(ref, {1: lambda items: ModelError("HTTP 500: out of memory")})
        res = pipeline.translate(cues, model, "Italian")
        failed = [r for r in res.attempt_log if r["codes"] == ["model_error"]]
        self.assertEqual(len(failed), 4)
        self.assertTrue(all(r["error"] == "HTTP 500: out of memory" for r in failed))
        self.assertTrue(all("error" not in r for r in res.attempt_log if r["codes"] != ["model_error"]))

    def test_a_model_that_is_always_down_leaves_everything_in_the_source_language(self):
        cues, ref = setup(4)
        model = Scripted(ref, {n: (lambda items: ModelError("down")) for n in range(1, 10)})
        res = pipeline.translate(cues, model, "Italian", max_retries=2)
        self.assertEqual([r.status for r in res.cues], ["fallback"] * 4)
        self.assertEqual([r.text for r in res.cues], [c.text for c in cues])
        self.assertEqual(res.latency_s, 0.0)


class PassthroughAndTargetTests(unittest.TestCase):
    def test_cues_without_letters_are_not_sent(self):
        cues = [Cue(1, 0, 2000, "Hello there my friend"), Cue(2, 2000, 4000, "♪♪"),
                Cue(3, 4000, 6000, "1234"), Cue(4, 6000, 8000, "Goodbye now friend")]
        ref = {"Hello there my friend": "Ciao a te amico", "Goodbye now friend": "Arrivederci amico"}
        model = Scripted(ref)
        res = pipeline.translate(cues, model, "Italian")
        self.assertEqual([i for i, _ in model.requests[0].cues], [1, 4])
        self.assertEqual([r.status for r in res.cues], ["ok", "passthrough", "passthrough", "ok"])
        self.assertEqual([r.text for r in res.cues][1:3], ["♪♪", "1234"])
        self.assertEqual(res.cues[1].attempts, 0)

    def test_nothing_to_translate_makes_no_call(self):
        res = pipeline.translate([Cue(1, 0, 1000, "♪")], Scripted({}), "Italian")
        self.assertEqual(res.calls, 0)

    def test_an_english_target_may_return_the_source(self):
        cues = [Cue(1, 0, 3000, "We keep the project safe")]
        identity = {cues[0].text: cues[0].text}
        for name, status in (("English", "ok"), ("en", "ok"), (" EN ", "ok"), ("Italian", "fallback")):
            res = pipeline.translate(cues, Scripted(identity), name, max_retries=0)
            self.assertEqual(res.cues[0].status, status, name)


class InvariantTests(unittest.TestCase):
    def test_no_cue_that_fails_a_check_is_ever_shipped(self):
        rates = Rates(drop=0.05, duplicate=0.05, merge=0.05, number=0.05, tag=0.05, long=0.05, english=0.05,
                      commentary=0.05, wrong_noun=0.0, fenced=0.1, truncated=0.1, stubborn=0.05)
        shipped = fallbacks = 0
        for seed in range(1, 31):
            cues, ref = synth.generate(seed, 40)
            model = ScriptedModel(ref, seed, rates)
            res = pipeline.translate(cues, model, "Italian")
            self.assertEqual([r.index for r in res.cues], [c.index for c in cues])
            for c, r in zip(cues, res.cues):
                if r.status in ("ok", "retried"):
                    shipped += 1
                    self.assertEqual(check_cue(c, r.text), [], (seed, c.index, r.text))
                elif r.status == "fallback":
                    fallbacks += 1
                    self.assertEqual(r.text, c.text)
        self.assertGreater(shipped, 900)
        self.assertGreater(fallbacks, 0)  # the setting is rough enough to exercise the fallback


if __name__ == "__main__":
    unittest.main()
