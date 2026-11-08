"""
Unit tests for Task 7: Server-Sent Events (SSE) Streaming Endpoint (/api/chat/stream).
Zero third-party pip dependencies - Python standard library only.
"""
import io
import json
import unittest
from unittest.mock import MagicMock, patch

import server


class TestChatStream(unittest.TestCase):
    def test_stream_filter_buffers_tags(self):
        # A generator emitting tokens containing a tag
        def token_gen():
            yield "Hello, "
            yield "I will check "
            yield "the files. [["
            yield "LIST_FILES: "
            yield "workspace"
            yield "]] Here "
            yield "they are."

        clean_chunks, tags = server.filter_stream_tags(token_gen())
        full_text = "".join(clean_chunks)
        self.assertNotIn("[[LIST_FILES", full_text)
        self.assertIn("Hello, I will check the files.", full_text)
        self.assertIn("Here they are.", full_text)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0][0], "LIST_FILES")
        self.assertEqual(tags[0][1], "workspace")

    def test_handler_chat_stream_headers_and_events(self):
        class DummyRequest:
            def makefile(self, *args, **kwargs):
                return io.BytesIO(b"")

        handler = server.Handler.__new__(server.Handler)
        handler.client_address = ("127.0.0.1", 12345)
        handler.command = "GET"
        handler.path = "/api/chat/stream?message=hello&mode=developer"
        handler.request_version = "HTTP/1.1"
        handler.requestline = f"{handler.command} {handler.path} {handler.request_version}"
        handler.wfile = io.BytesIO()
        handler.headers = {"Host": "127.0.0.1:8765", "Cookie": f"nova_session={server.SESSION_TOKEN}", "X-Nova-Token": server.API_SESSION_TOKEN}

        with patch("server.chat", return_value={"reply": "Hi from streaming!", "actions": []}):
            handler.do_GET()

        response_bytes = handler.wfile.getvalue()
        response_text = response_bytes.decode("utf-8", errors="replace")

        self.assertIn("text/event-stream", response_text)
        self.assertIn("data: ", response_text)
        self.assertIn("Hi from streaming!", response_text)


if __name__ == "__main__":
    unittest.main()
