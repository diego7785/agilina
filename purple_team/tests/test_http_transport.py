"""Tests for the shared HTTP transport: redirections are refused, without any network.

A fake ``http`` handler answers in memory before the real ``HTTPHandler`` is ever asked, so
the whole ``urllib`` machinery (error processor, redirect handler) runs without sockets.
"""

import io
import unittest
import urllib.request
import urllib.response
from email.message import Message

from purple_team.providers.base import ProviderRequestError
from purple_team.providers.http_transport import (
    REDACTED,
    NoRedirectHandler,
    UrllibTransport,
    build_opener,
    redact_secrets,
)

FAKE_KEY = "clave-falsa-de-prueba"
ORIGIN = "http://api.example.com/v1/models/m"
ELSEWHERE = "http://otro.example.org/captura"
KEY_HEADER = "X-goog-api-key"
FOUND = 302
OK = 200
FIRST_HANDLER = 100


class InMemoryHttpHandler(urllib.request.BaseHandler):
    """Answers ``http`` requests from memory: a redirection for ``ORIGIN``, 200 elsewhere."""

    handler_order = FIRST_HANDLER

    def __init__(self) -> None:
        self.seen: list[tuple[str, str | None]] = []

    def http_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        self.seen.append((req.full_url, req.get_header(KEY_HEADER)))
        headers = Message()
        if req.full_url == ORIGIN:
            headers["Location"] = ELSEWHERE
            response = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, FOUND)
            response.msg = "Found"
            return response
        response = urllib.response.addinfourl(io.BytesIO(b"{}"), headers, req.full_url, OK)
        response.msg = "OK"
        return response


def request_with_key() -> urllib.request.Request:
    return urllib.request.Request(ORIGIN, headers={KEY_HEADER: FAKE_KEY})


class RedirectTest(unittest.TestCase):
    def test_stock_urllib_would_forward_the_key_to_the_new_location(self) -> None:
        handler = InMemoryHttpHandler()
        stock = urllib.request.build_opener(urllib.request.ProxyHandler({}), handler)
        with stock.open(request_with_key(), timeout=1.0):
            pass
        self.assertEqual(handler.seen, [(ORIGIN, FAKE_KEY), (ELSEWHERE, FAKE_KEY)])

    def test_the_harness_opener_never_follows_a_redirection(self) -> None:
        handler = InMemoryHttpHandler()
        opener = build_opener()
        opener.add_handler(handler)
        redirect_handlers = [
            item for item in opener.handlers if isinstance(item, urllib.request.HTTPRedirectHandler)
        ]
        self.assertTrue(redirect_handlers)
        self.assertTrue(all(isinstance(item, NoRedirectHandler) for item in redirect_handlers))
        transport = UrllibTransport("Gemini", frozenset({"http"}), opener)
        headers = {"x-goog-api-key": FAKE_KEY}
        with self.assertRaises(ProviderRequestError) as raised:
            transport.request_json("GET", ORIGIN, None, 1.0, headers=headers, redact=(FAKE_KEY,))
        message = str(raised.exception)
        self.assertIn("redirección HTTP 302", message)
        self.assertIn("no sigue redirecciones", message)
        self.assertNotIn(FAKE_KEY, message)
        self.assertEqual(handler.seen, [(ORIGIN, FAKE_KEY)])


class RedactSecretsTest(unittest.TestCase):
    def test_every_non_empty_secret_is_replaced(self) -> None:
        message = f"API key {FAKE_KEY} not valid ({FAKE_KEY})"
        self.assertEqual(
            redact_secrets(message, ("", FAKE_KEY)),
            f"API key {REDACTED} not valid ({REDACTED})",
        )


if __name__ == "__main__":
    unittest.main()
