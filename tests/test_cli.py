import contextlib
import io
import json
import os
import tempfile
import time
import unittest

from subtitle_translate import cli, srt
from tests.stub_server import StubServer, completion


def run(argv):
    """(exit code, what the command wrote to stderr)"""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, err.getvalue()

SRC = (
    "1\n00:00:00,000 --> 00:00:02,000\nHello there my friend\n\n"
    "2\n00:00:02,500 --> 00:00:04,000\n<i>Thank you very much</i>\n"
)
ANSWERS = {"Hello there my friend": "Ciao a te amico", "<i>Thank you very much</i>": "<i>Grazie mille</i>"}


def respond(body):
    asked = json.loads(body["messages"][1]["content"].split("\n")[0])
    return 200, completion(json.dumps([{"id": a["id"], "text": ANSWERS[a["text"]]} for a in asked]))


def echo(body):
    """A server that sends every cue back untranslated."""
    asked = json.loads(body["messages"][1]["content"].split("\n")[0])
    return 200, completion(json.dumps([{"id": a["id"], "text": a["text"]} for a in asked]))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = os.path.join(self.tmp.name, "in.srt")
        self.out = os.path.join(self.tmp.name, "out.srt")
        self.report = os.path.join(self.tmp.name, "report.json")
        with open(self.src, "w", encoding="utf-8", newline="") as fh:
            fh.write(SRC.replace("\n", "\r\n"))

    def args(self, srv, *extra):
        return ["translate", self.src, "--to", "Italian", "--out", self.out, "--report", self.report,
                "--base-url", srv.base_url, "--model", "m", *extra]

    def test_translates_and_writes_the_file_and_a_report(self):
        with StubServer(respond) as srv:
            code, err = run(self.args(srv))
        self.assertEqual(code, 0)
        self.assertIn("2 cues, 1 calls", err)
        with open(self.out, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\r", raw)
        cues = srt.parse(raw.decode("utf-8"))
        self.assertEqual([(c.index, c.start_ms, c.end_ms) for c in cues], [(1, 0, 2000), (2, 2500, 4000)])
        self.assertEqual([c.text for c in cues], ["Ciao a te amico", "<i>Grazie mille</i>"])
        with open(self.report, encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["status"], {"ok": 2})
        self.assertEqual((rep["left_in_source"], rep["rejected"]), ([], []))

    def test_rules_are_passed_through(self):
        with StubServer(respond) as srv:
            run(self.args(srv, "--max-lines", "1", "--max-line-chars", "30"))
        system = srv.requests[0]["body"]["messages"][0]["content"]
        self.assertIn("1 line of 30 characters", system)

    def test_refuses_to_overwrite_unless_forced(self):
        for path in (self.out, self.report):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("keep me")
        with StubServer(respond) as srv:
            code, err = run(self.args(srv))
            self.assertEqual(code, 2)
            self.assertIn("--force", err)
            self.assertEqual(srv.requests, [])
            with open(self.out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "keep me")
            self.assertEqual(run(self.args(srv, "--force"))[0], 0)
        with open(self.out, encoding="utf-8") as fh:
            self.assertNotEqual(fh.read(), "keep me")

    def test_out_alone_is_also_protected(self):
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        with StubServer(respond) as srv:
            self.assertEqual(run(self.args(srv))[0], 2)
            self.assertEqual(srv.requests, [])
        self.assertFalse(os.path.exists(self.report))
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep me")

    def test_settings_that_cannot_work_are_refused_before_anything_is_sent(self):
        for flag, value in (("--batch", "0"), ("--retries", "-1"), ("--max-lines", "0"),
                            ("--max-line-chars", "0"), ("--max-cps", "0"), ("--timeout", "0")):
            with StubServer(respond) as srv:
                code, err = run(self.args(srv, flag, value))
                self.assertEqual((code, srv.requests), (2, []), flag)
            self.assertIn(flag, err)
            self.assertFalse(os.path.exists(self.out), flag)

    def test_max_cps_flag_changes_what_is_rejected(self):
        # Both answers read at 7 to 8 characters per second.
        with StubServer(respond) as srv:
            run(self.args(srv, "--max-cps", "5", "--retries", "0"))
        with open(self.report, encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["status"], {"fallback": 2})
        self.assertEqual([r["codes"] for r in rep["rejected"]], [["reading_speed"], ["reading_speed"]])

    def test_timeout_flag_stops_waiting_for_a_slow_server(self):
        def slow(body):
            time.sleep(1.0)
            return respond(body)

        with StubServer(slow) as srv:
            code, _ = run(self.args(srv, "--timeout", "0.2", "--retries", "0"))
        self.assertEqual(code, 0)
        with open(self.report, encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["status"], {"fallback": 2})
        self.assertEqual({tuple(r["codes"]) for r in rep["rejected"]}, {("model_error",)})

    def test_report_alone_is_also_protected(self):
        with open(self.report, "w", encoding="utf-8") as fh:
            fh.write("keep me")
        with StubServer(respond) as srv:
            self.assertEqual(run(self.args(srv))[0], 2)
        self.assertFalse(os.path.exists(self.out))

    def test_unreadable_input_makes_no_output(self):
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write("1\nnot a timing\nHi\n")
        with StubServer(respond) as srv:
            code, err = run(self.args(srv))
            self.assertEqual(code, 2)
            self.assertIn("cannot read", err)
            self.assertEqual(srv.requests, [])
        self.assertFalse(os.path.exists(self.out))

    def write_one_cue(self):
        with open(self.src, "w", encoding="utf-8") as fh:
            fh.write("1\n00:00:00,000 --> 00:00:03,000\nWe keep the project safe\n")

    def test_a_cue_that_never_passes_is_left_in_the_source_and_reported(self):
        self.write_one_cue()
        with StubServer(echo) as srv:
            code, _ = run(self.args(srv))
            asked = len(srv.requests)
        self.assertEqual((code, asked), (0, 3))
        with open(self.report, encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertEqual(rep["status"], {"fallback": 1})
        self.assertEqual(rep["left_in_source"], [1])
        self.assertEqual([(r["attempt"], r["codes"]) for r in rep["rejected"]],
                         [(1, ["unchanged"]), (2, ["unchanged"]), (3, ["unchanged"])])
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(srt.parse(fh.read())[0].text, "We keep the project safe")

    def test_retries_flag_sets_the_number_of_extra_attempts(self):
        self.write_one_cue()
        with StubServer(echo) as srv:
            run(self.args(srv, "--retries", "0"))
            self.assertEqual(len(srv.requests), 1)

    def test_batch_flag_sets_the_cues_per_request(self):
        with StubServer(respond) as srv:
            run(self.args(srv, "--batch", "1"))
            asked = [len(json.loads(q["body"]["messages"][1]["content"].split("\n")[0])) for q in srv.requests]
        self.assertEqual(asked, [1, 1])

    def test_api_key_and_temperature_reach_the_server(self):
        with StubServer(respond) as srv:
            run(self.args(srv, "--api-key", "test-key", "--temperature", "0.2"))
        sent = srv.requests[0]
        self.assertEqual(sent["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(sent["body"]["temperature"], 0.2)

    def test_missing_input(self):
        os.remove(self.src)
        with StubServer(respond) as srv:
            self.assertEqual(run(self.args(srv))[0], 2)

    def test_input_that_is_not_utf8(self):
        with open(self.src, "wb") as fh:
            fh.write(b"1\n00:00:00,000 --> 00:00:02,000\n\xff\xfe\n")
        with StubServer(respond) as srv:
            self.assertEqual(run(self.args(srv))[0], 2)


if __name__ == "__main__":
    unittest.main()
