"""A local HTTP server that answers /chat/completions the way a model server does."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class StubServer:
    """`respond(request_body) -> (status, body_text)`; requests are kept in `.requests`."""

    def __init__(self, respond):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                status, text = respond(body)
                data = text.encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # the client gave up (a timeout test)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self):
        return "http://127.0.0.1:%d/v1" % self.httpd.server_address[1]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def completion(content):
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})
