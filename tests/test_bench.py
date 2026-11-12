import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from subtitle_translate import bench, pipeline, synth
from subtitle_translate.scripted import Rates, ScriptedModel
from tests.stub_server import StubServer, completion

ZERO = dict.fromkeys(
    ["drop", "duplicate", "merge", "number", "tag", "long", "english", "commentary", "wrong_noun",
     "fenced", "truncated", "stubborn"], 0.0)


class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = bench.run_standin(seeds=(1, 2, 3), files=2, cues_per_file=60)
        cls.p = cls.data["pooled"]

    def test_counts_add_up(self):
        p = self.p
        self.assertEqual(p["first_reply_clean"] + p["first_reply_wrong"], p["cues"])
        self.assertEqual(p["shipped_right"] + p["shipped_wrong"] + p["left_in_source"], p["cues"])
        self.assertEqual(sum(p["first_reply_wrong_by"].values()), p["first_reply_wrong"])
        self.assertEqual(sum(p["shipped_wrong_by"].values()), p["shipped_wrong"])
        self.assertEqual(sum(r["cues"] for r in self.data["per_seed"]), p["cues"])

    def test_the_checks_cut_the_wrong_cues_that_ship(self):
        self.assertLess(self.p["shipped_wrong"] * 4, self.p["first_reply_wrong"])

    def test_retries_turn_rejected_cues_into_shipped_ones(self):
        none = bench.run_standin(seeds=(1, 2, 3), files=2, cues_per_file=60, retries=0)["pooled"]
        self.assertGreater(none["left_in_source"], self.p["left_in_source"])
        self.assertLess(none["shipped_right"], self.p["shipped_right"])

    def test_retries_cost_calls_and_scripted_time(self):
        self.assertGreater(self.p["calls_with_retries"], self.p["calls_first_reply"])
        self.assertGreater(self.p["latency_with_retries_s"], self.p["latency_first_reply_s"])

    def test_correct_outputs_are_never_rejected(self):
        self.assertGreater(self.p["trials"]["clean"], 300)
        self.assertEqual(self.p["rejected"].get("clean", 0), 0)

    def test_mechanical_faults_are_all_rejected(self):
        for kind in ("drop", "duplicate", "merge", "merged_away", "number", "long", "commentary", "truncated"):
            self.assertGreater(self.p["trials"].get(kind, 0), 0, kind)
            self.assertEqual(self.p["rejected"].get(kind, 0), self.p["trials"][kind], kind)

    def test_a_changed_noun_gets_through(self):
        self.assertGreater(self.p["shipped_wrong_by"].get("wrong_noun", 0), 0)

    def test_hand_built_case(self):
        # Every attempt at a cue with a digit gets its number changed; the rest is right.
        cues, ref = synth.generate(4, 30)
        model = ScriptedModel(ref, 4, Rates(**dict(ZERO, number=1.0)))
        res = pipeline.translate(cues, model, "Italian")
        s = bench.score_run(res, model.log)
        with_digit = sum(1 for c in cues if any(ch.isdigit() for ch in ref[c.text]))
        self.assertGreater(with_digit, 5)
        self.assertEqual(s["cues"], 30)
        self.assertEqual(s["first_reply_wrong"], with_digit)
        self.assertEqual(s["left_in_source"], with_digit)
        self.assertEqual(s["shipped_right"], 30 - with_digit)
        self.assertEqual(s["shipped_wrong"], 0)
        self.assertEqual(s["trials"]["number"], 3 * with_digit)
        self.assertEqual(s["rejected"]["number"], 3 * with_digit)


class RenderTests(unittest.TestCase):
    def test_percentages_are_whole_numbers(self):
        self.assertEqual((bench._pct(1, 4), bench._pct(1, 3), bench._pct(5, 5), bench._pct(0, 0)),
                         ("25%", "33%", "100%", "n/a"))

    def test_standin_table_has_a_row_per_seed_and_a_total(self):
        data = bench.run_standin(seeds=(1, 2), files=1, cues_per_file=20)
        text = bench.render_standin(data)
        self.assertIn("| 1 |", text)
        self.assertIn("| 2 |", text)
        self.assertIn("| all |", text)
        self.assertIn("Outputs with no fault:", text)

    def test_live_table(self):
        data = {
            "setup": {"source": "demo.srt", "model": "m", "target": "Italian", "runs": 1, "temperature": 0.3,
                      "batch_size": 8, "max_retries": 2},
            "runs": [{"run": 1, "wall_s": 12.6, "rejected": [{"attempt": 1}, {"attempt": 2}],
                      "summary": {"cues": 10, "calls": 4, "reflowed": 3, "status": {"ok": 8, "retried": 1, "fallback": 1},
                                  "first_attempt_codes": {"numbers": 2, "tags": 1}}}],
        }
        text = bench.render_live(data)
        self.assertIn("| 1 | 10 | 1 | 8 / 1 / 1 | 3 | 4 | 13 |", text)
        self.assertIn("numbers 2, tags 1", text)

    def test_live_table_when_nothing_was_rejected(self):
        data = {
            "setup": {"source": "demo.srt", "model": "m", "target": "Italian", "runs": 1, "temperature": 0.3},
            "runs": [{"run": 1, "wall_s": 1.0, "rejected": [],
                      "summary": {"cues": 3, "calls": 1, "reflowed": 0, "status": {"ok": 3}, "first_attempt_codes": {}}}],
        }
        self.assertIn("nothing was rejected", bench.render_live(data))


class LiveRunTests(unittest.TestCase):
    def test_run_live_against_a_local_server(self):
        answers = {"Hello there my friend": "Ciao a te amico", "Thank you very much": "Grazie mille"}

        def respond(body):
            asked = json.loads(body["messages"][1]["content"].split("\n")[0])
            return 200, completion(json.dumps([{"id": a["id"], "text": answers[a["text"]]} for a in asked]))

        src = "1\n00:00:00,000 --> 00:00:02,000\nHello there my friend\n\n2\n00:00:02,000 --> 00:00:04,000\nThank you very much\n"
        with tempfile.TemporaryDirectory() as d, StubServer(respond) as srv:
            path = os.path.join(d, "in.srt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            data = bench.run_live(path, srv.base_url, "m", runs=2, temperature=0.3, target="Italian", batch=8, retries=2)
        self.assertEqual([r["run"] for r in data["runs"]], [1, 2])
        for r in data["runs"]:
            self.assertEqual(r["summary"]["status"], {"ok": 2})
            self.assertEqual(r["rejected"], [])
        self.assertEqual([q["body"]["seed"] for q in srv.requests], [1, 2])
        self.assertEqual([r["seed"] for r in data["runs"]], [1, 2])
        self.assertEqual(data["setup"]["source"], "in.srt")

    def test_live_run_records_what_was_rejected(self):
        def respond(body):
            asked = json.loads(body["messages"][1]["content"].split("\n")[0])
            return 200, completion(json.dumps([{"id": a["id"], "text": a["text"]} for a in asked]))

        src = "1\n00:00:00,000 --> 00:00:03,000\nWe keep the project safe\n"
        with tempfile.TemporaryDirectory() as d, StubServer(respond) as srv:
            path = os.path.join(d, "in.srt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            data = bench.run_live(path, srv.base_url, "m", runs=1, temperature=0.0, target="Italian", batch=8, retries=1)
        run = data["runs"][0]
        self.assertEqual(run["summary"]["status"], {"fallback": 1})
        self.assertEqual([(x["attempt"], x["codes"]) for x in run["rejected"]], [(1, ["unchanged"]), (2, ["unchanged"])])
        self.assertEqual(run["rejected"][0]["output"], "We keep the project safe")


    def test_live_run_keeps_the_servers_error_message(self):
        src = "1\n00:00:00,000 --> 00:00:03,000\nWe keep the project safe\n"
        refusal = json.dumps({"error": {"message": "prediction aborted"}})
        with tempfile.TemporaryDirectory() as d, StubServer(lambda body: (500, refusal)) as srv:
            path = os.path.join(d, "in.srt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            data = bench.run_live(path, srv.base_url, "m", runs=1, temperature=0.0, target="Italian", batch=8, retries=0)
        row = data["runs"][0]["rejected"][0]
        self.assertEqual(row["codes"], ["model_error"])
        self.assertIn("prediction aborted", row["error"])


class CheckCommandTests(unittest.TestCase):
    """bench readme and bench check on a small stand-in in a temporary folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        results = os.path.join(tmp.name, "results")
        os.makedirs(results)
        self.stored = os.path.join(results, "standin.json")
        self.readme = os.path.join(tmp.name, "README.md")
        with open(self.stored, "w", encoding="utf-8") as fh:
            json.dump(bench.run_standin(seeds=(1, 2), files=1, cues_per_file=20), fh)
        with open(self.readme, "w", encoding="utf-8") as fh:
            fh.write("intro\n\n<!-- standin:start -->\n\n<!-- standin:end -->\n\noutro\n")
        for name, value in (("RESULTS", results), ("README", self.readme)):
            patcher = mock.patch.object(bench, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return bench.check()

    def readme_text(self):
        with open(self.readme, encoding="utf-8") as fh:
            return fh.read()

    def test_readme_command_fills_the_block_and_check_then_passes(self):
        bench.write_readme()
        text = self.readme_text()
        self.assertIn("| all |", text)
        self.assertTrue(text.startswith("intro\n") and text.endswith("outro\n"))
        self.assertEqual(self.check(), 0)

    def test_check_fails_when_a_table_in_the_readme_is_edited(self):
        bench.write_readme()
        with open(self.readme, "w", encoding="utf-8") as fh:
            fh.write(self.readme_text().replace("| all |", "| every |"))
        self.assertEqual(self.check(), 1)

    def test_check_fails_when_the_stored_results_differ_from_a_fresh_run(self):
        bench.write_readme()
        with open(self.stored, encoding="utf-8") as fh:
            data = json.load(fh)
        data["per_seed"][0]["reflowed"] += 1   # shown in no table, so only the fresh run can notice
        with open(self.stored, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        self.assertEqual(self.check(), 1)


class StoredResultsTests(unittest.TestCase):
    def test_results_and_readme_agree_with_a_fresh_run(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = bench.check()
        self.assertEqual(code, 0, out.getvalue())

    def test_the_standin_numbers_quoted_in_the_readme_prose_match_the_stored_results(self):
        with open(os.path.join(bench.RESULTS, "standin.json"), encoding="utf-8") as fh:
            pooled = json.load(fh)["pooled"]
        with open(bench.README, encoding="utf-8") as fh:
            text = fh.read()
        noun = "%d of the %d wrong-noun cues" % (pooled["shipped_wrong_by"]["wrong_noun"], pooled["trials"]["wrong_noun"])
        english = "%d of the %d English replies" % (pooled["shipped_wrong_by"]["english"], pooled["trials"]["english"])
        self.assertIn(noun, text)
        self.assertIn(english, text)


if __name__ == "__main__":
    unittest.main()
