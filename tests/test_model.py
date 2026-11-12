import json
import socket
import time
import unittest

from subtitle_translate.checks import CODES, Rules
from subtitle_translate.model import PROBLEMS, ModelError, OpenAIChat, Request, build_messages, parse_reply
from tests.stub_server import StubServer, completion


class ParseReplyTests(unittest.TestCase):
    def test_plain_array(self):
        self.assertEqual(parse_reply('[{"id": 1, "text": "a"}]'), ([{"id": 1, "text": "a"}], False))

    def test_empty_array_is_a_reply(self):
        self.assertEqual(parse_reply("[]"), ([], False))

    def test_code_fence_is_repaired(self):
        items, repaired = parse_reply('```json\n[{"id": 1, "text": "a"}]\n```')
        self.assertEqual(items, [{"id": 1, "text": "a"}])
        self.assertTrue(repaired)

    def test_sentence_around_the_array_is_repaired(self):
        items, repaired = parse_reply('Here you go: [{"id": 2, "text": "b"}] Hope it helps.')
        self.assertEqual(items[0]["id"], 2)
        self.assertTrue(repaired)

    def test_unreadable_replies(self):
        for raw in ("", "no json here", '[{"id": 1, "text": "cut off', '{"id": 1, "text": "a"}',
                    "[1, 2, 3]", '["a", "b"]', "]["):
            self.assertEqual(parse_reply(raw), (None, False), raw)


class BuildMessagesTests(unittest.TestCase):
    def test_every_code_has_a_sentence_for_the_model(self):
        for code in CODES + ("missing", "duplicate", "bad_reply", "model_error"):
            self.assertIn(code, PROBLEMS)

    def test_first_request(self):
        msgs = build_messages(Request("Italian", [(1, "Hello"), (2, "Bye")], rules=Rules(max_lines=2, max_line_chars=40)))
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        self.assertIn("into Italian", msgs[0]["content"])
        self.assertIn("2 lines of 40 characters", msgs[0]["content"])
        self.assertEqual(json.loads(msgs[1]["content"]), [{"id": 1, "text": "Hello"}, {"id": 2, "text": "Bye"}])

    def test_retry_names_the_problems_in_words(self):
        msgs = build_messages(Request("Italian", [(3, "It takes 12 seconds")], {3: ["numbers", "tags"]}))
        user = msgs[1]["content"]
        self.assertIn("rejected last time", user)
        self.assertIn("the numbers did not match the source", user)
        self.assertIn("the tags did not match the source", user)

    def test_no_feedback_text_on_a_first_request(self):
        self.assertNotIn("rejected", build_messages(Request("Italian", [(1, "Hello")]))[1]["content"])


class OpenAIChatTests(unittest.TestCase):
    def request(self):
        return Request("Italian", [(1, "Hello")])

    def test_success_sends_the_chat_completions_request(self):
        with StubServer(lambda body: (200, completion('[{"id": 1, "text": "Ciao"}]'))) as srv:
            client = OpenAIChat(srv.base_url, "some-model", api_key="k", temperature=0.2, seed=7)
            reply = client.translate(self.request())
        self.assertEqual(json.loads(reply.text), [{"id": 1, "text": "Ciao"}])
        self.assertGreaterEqual(reply.latency_s, 0.0)
        sent = srv.requests[0]
        self.assertEqual(sent["path"], "/v1/chat/completions")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer k")
        body = sent["body"]
        self.assertEqual((body["model"], body["temperature"], body["seed"], body["stream"]), ("some-model", 0.2, 7, False))
        self.assertEqual(len(body["messages"]), 2)

    def test_no_seed_when_none_is_given(self):
        with StubServer(lambda body: (200, completion("[]"))) as srv:
            OpenAIChat(srv.base_url, "m").translate(self.request())
        self.assertNotIn("seed", srv.requests[0]["body"])

    def test_failures_become_model_errors(self):
        cases = {
            "http 500": (500, "oops"),
            "not json": (200, "<html>"),
            "no choices": (200, json.dumps({"choices": []})),
            "no message": (200, json.dumps({"choices": [{}]})),
            "null content": (200, completion(None)),
            "list content": (200, completion(["a"])),
        }
        for name, answer in cases.items():
            with StubServer(lambda body, a=answer: a) as srv:
                with self.assertRaises(ModelError, msg=name):
                    OpenAIChat(srv.base_url, "m").translate(self.request())

    def test_an_http_error_carries_the_servers_message(self):
        body = json.dumps({"error": {"message": "prediction aborted, token repeat limit reached"}})
        with StubServer(lambda b: (500, body)) as srv:
            with self.assertRaises(ModelError) as ctx:
                OpenAIChat(srv.base_url, "m").translate(self.request())
        self.assertIn("HTTP 500", str(ctx.exception))
        self.assertIn("token repeat limit reached", str(ctx.exception))

    def test_an_http_error_with_no_body_still_names_the_status(self):
        with StubServer(lambda b: (503, "")) as srv:
            with self.assertRaises(ModelError) as ctx:
                OpenAIChat(srv.base_url, "m").translate(self.request())
        self.assertIn("HTTP 503", str(ctx.exception))

    def test_a_server_slower_than_the_timeout_is_a_model_error(self):
        def slow(body):
            time.sleep(1.0)
            return 200, completion("[]")

        with StubServer(slow) as srv:
            with self.assertRaises(ModelError):
                OpenAIChat(srv.base_url, "m", timeout_s=0.2).translate(self.request())

    def test_connection_refused_is_a_model_error(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(ModelError):
            OpenAIChat("http://127.0.0.1:%d/v1" % port, "m", timeout_s=2).translate(self.request())


if __name__ == "__main__":
    unittest.main()
