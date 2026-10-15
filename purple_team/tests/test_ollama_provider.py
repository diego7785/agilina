"""Tests for the Ollama adapter; no test opens a real connection.

The provider is exercised with a fake ``JsonTransport`` and the transport with a fake
opener, so every failure mode (server down, HTTP 500, timeout, invalid body) is simulated.
"""

import io
import json
import unittest
import urllib.error
from collections.abc import Mapping
from dataclasses import replace
from email.message import Message
from typing import Self
from unittest import mock

from purple_team.config import OllamaFormat, OllamaSettings
from purple_team.core.models import ceremony_output_json_schema
from purple_team.core.output_parser import parse_ceremony_output
from purple_team.errors import ConfigError
from purple_team.providers.base import (
    ModelProvider,
    ModelRequest,
    ProviderRequestError,
    ProviderUnavailableError,
    RequestTrace,
)
from purple_team.providers.http_transport import Opener, UrllibTransport
from purple_team.providers.ollama import (
    ALLOWED_SCHEMES,
    OLLAMA_SERVICE,
    OllamaProvider,
    build_chat_payload,
    parse_chat_response,
    parse_chat_thinking,
)

BASE_URL = "http://localhost:11434"
MODEL = "qwen3.5:4b"
TIMEOUT = 45.0
SETTINGS = OllamaSettings(
    base_url=BASE_URL,
    model=MODEL,
    timeout_seconds=TIMEOUT,
    temperature=0.9,
    think=False,
    output_format=OllamaFormat.JSON,
)
REQUEST = ModelRequest(
    system_prompt="Eres Agilina.",
    user_content="<transcripcion>...</transcripcion>",
    trace=RequestTrace(run_id="run-1", case_id="c00-control"),
    temperature=0.2,
)
CLOSING = {
    "summary": "Daily sin bloqueos.",
    "action_items": [
        {
            "destination": "jira_comment",
            "target": "AGI-231",
            "title": "Comentario",
            "content": "Comentar la causa.",
        },
    ],
}
TAGS_BODY = {"models": [{"name": MODEL, "model": MODEL}]}


def ollama_transport(opener: Opener) -> UrllibTransport:
    """The transport the Ollama adapter builds, with a fake opener."""
    return UrllibTransport(OLLAMA_SERVICE, ALLOWED_SCHEMES, opener)


def settings_with(**changes: object) -> OllamaSettings:
    """Copy of ``SETTINGS`` with some fields replaced."""
    return replace(SETTINGS, **changes)


def chat_body(content: str, thinking: str | None = None) -> dict[str, object]:
    """Body of a ``/api/chat`` answer."""
    message: dict[str, object] = {"role": "assistant", "content": content}
    if thinking is not None:
        message["thinking"] = thinking
    return {"model": MODEL, "message": message, "done": True}


class FakeTransport:
    """Records every call and answers with a fixed body or raises a fixed error."""

    def __init__(
        self,
        body: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.body = body if body is not None else {}
        self.error = error
        self.calls: list[tuple[str, str, Mapping[str, object] | None, float]] = []

    def request_json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        timeout: float,
    ) -> Mapping[str, object]:
        self.calls.append((method, url, payload, timeout))
        if self.error is not None:
            raise self.error
        return self.body


class FakeResponse:
    """Minimal HTTP response for the fake opener."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class FakeOpener:
    """Opener that never touches the network: it returns a response or raises an error."""

    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.requests: list[tuple[str, str, bytes | None, float]] = []

    def open(self, request: object, *, timeout: float) -> FakeResponse:
        full_url = getattr(request, "full_url", "")
        method = getattr(request, "method", "")
        data = getattr(request, "data", None)
        self.requests.append((method, full_url, data, timeout))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class ChatPayloadTest(unittest.TestCase):
    def test_payload_uses_request_temperature_think_and_json_format(self) -> None:
        payload = build_chat_payload(REQUEST, SETTINGS)
        expected = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "Eres Agilina."},
                {"role": "user", "content": "<transcripcion>...</transcripcion>"},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2},
            "format": "json",
        }
        self.assertEqual(payload, expected)

    def test_think_is_sent_as_configured(self) -> None:
        payload = build_chat_payload(REQUEST, settings_with(think=True))
        self.assertIs(payload["think"], True)

    def test_schema_format_sends_the_json_schema_of_the_closing(self) -> None:
        payload = build_chat_payload(REQUEST, settings_with(output_format=OllamaFormat.SCHEMA))
        self.assertEqual(payload["format"], ceremony_output_json_schema())

    def test_none_format_omits_the_field(self) -> None:
        payload = build_chat_payload(REQUEST, settings_with(output_format=OllamaFormat.NONE))
        self.assertNotIn("format", payload)

    def test_schema_requires_the_fields_the_parser_requires(self) -> None:
        schema = ceremony_output_json_schema()
        self.assertEqual(schema["required"], ["summary", "action_items"])
        properties = schema["properties"]
        assert isinstance(properties, dict)
        items = properties["action_items"]["items"]
        self.assertEqual(items["required"], ["destination", "title", "content"])
        destinations = items["properties"]["destination"]["enum"]
        self.assertEqual(destinations, ["jira_comment", "calendar_event", "slack_message"])
        self.assertEqual(items["properties"]["invitees"]["type"], "array")
        self.assertEqual(items["properties"]["target"], {"type": "string"})


class ChatResponseTest(unittest.TestCase):
    def test_parses_content_and_thinking(self) -> None:
        body = chat_body('{"summary": "x"}', thinking="razonamiento")
        self.assertEqual(parse_chat_response(body), '{"summary": "x"}')
        self.assertEqual(parse_chat_thinking(body), "razonamiento")

    def test_missing_or_empty_thinking_is_none(self) -> None:
        self.assertIsNone(parse_chat_thinking(chat_body("x")))
        self.assertIsNone(parse_chat_thinking(chat_body("x", thinking="")))

    def test_rejects_malformed_chat_responses(self) -> None:
        for body in ({}, {"message": "x"}, {"message": {"content": 3}}):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    parse_chat_response(body)
        with self.assertRaises(ValueError):
            parse_chat_thinking({"message": {"content": "x", "thinking": 3}})


class EnsureAvailableTest(unittest.TestCase):
    def test_passes_when_the_model_is_downloaded(self) -> None:
        transport = FakeTransport(body=TAGS_BODY)
        provider = OllamaProvider(SETTINGS, transport)
        self.assertIsInstance(provider, ModelProvider)
        provider.ensure_available()
        self.assertEqual(transport.calls, [("GET", f"{BASE_URL}/api/tags", None, TIMEOUT)])

    def test_untagged_model_matches_latest(self) -> None:
        transport = FakeTransport(body={"models": [{"name": "llama3:latest"}]})
        OllamaProvider(settings_with(model="llama3"), transport).ensure_available()

    def test_missing_model_suggests_ollama_pull(self) -> None:
        transport = FakeTransport(body={"models": [{"name": "otro:1b", "model": "otro:1b"}]})
        with self.assertRaises(ProviderUnavailableError) as raised:
            OllamaProvider(SETTINGS, transport).ensure_available()
        self.assertIn(f"ollama pull {MODEL}", str(raised.exception))

    def test_server_down_is_unavailable(self) -> None:
        transport = FakeTransport(error=ProviderRequestError("connection refused"))
        with self.assertRaises(ProviderUnavailableError) as raised:
            OllamaProvider(SETTINGS, transport).ensure_available()
        self.assertIn("ollama serve", str(raised.exception))

    def test_tags_without_models_list_is_unavailable(self) -> None:
        with self.assertRaises(ProviderUnavailableError):
            OllamaProvider(SETTINGS, FakeTransport(body={"x": 1})).ensure_available()

    def test_rejects_base_urls_that_are_not_http(self) -> None:
        for base_url in ("file:///etc/passwd", "ftp://localhost:11434", "localhost:11434", ""):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ConfigError):
                    OllamaProvider(settings_with(base_url=base_url), FakeTransport())


class CompleteTest(unittest.TestCase):
    def test_posts_the_payload_and_returns_content_and_thinking(self) -> None:
        content = json.dumps(CLOSING)
        transport = FakeTransport(body=chat_body(content, thinking="pienso"))
        response = OllamaProvider(settings_with(think=True), transport).complete(REQUEST)
        self.assertEqual(response.text, content)
        self.assertEqual(response.thinking, "pienso")
        self.assertEqual((response.provider, response.model), ("ollama", MODEL))
        method, url, payload, timeout = transport.calls[0]
        self.assertEqual((method, url, timeout), ("POST", f"{BASE_URL}/api/chat", TIMEOUT))
        self.assertEqual(payload, build_chat_payload(REQUEST, settings_with(think=True)))

    def test_thinking_is_not_mixed_into_the_text(self) -> None:
        transport = FakeTransport(body=chat_body("{}", thinking="pienso"))
        response = OllamaProvider(SETTINGS, transport).complete(REQUEST)
        self.assertNotIn("pienso", response.text)

    def test_transport_failure_propagates_as_provider_request_error(self) -> None:
        transport = FakeTransport(error=ProviderRequestError("timeout"))
        with self.assertRaises(ProviderRequestError):
            OllamaProvider(SETTINGS, transport).complete(REQUEST)

    def test_body_without_message_is_a_provider_request_error(self) -> None:
        with self.assertRaises(ProviderRequestError):
            OllamaProvider(SETTINGS, FakeTransport(body={"done": True})).complete(REQUEST)

    def test_think_blocks_and_fences_in_the_content_still_parse(self) -> None:
        content = "<think>\nprimero pienso\n</think>\n```json\n" + json.dumps(CLOSING) + "\n```"
        provider = OllamaProvider(SETTINGS, FakeTransport(body=chat_body(content)))
        response = provider.complete(REQUEST)
        self.assertEqual(response.text, content)
        output = parse_ceremony_output(response.text)
        self.assertEqual(output.summary, "Daily sin bloqueos.")


class UrllibTransportTest(unittest.TestCase):
    def test_sends_json_and_decodes_the_answer(self) -> None:
        opener = FakeOpener(FakeResponse(200, json.dumps(TAGS_BODY).encode()))
        body = ollama_transport(opener).request_json("POST", f"{BASE_URL}/api/chat", {"a": 1}, 5.0)
        self.assertEqual(body, TAGS_BODY)
        self.assertEqual(opener.requests, [("POST", f"{BASE_URL}/api/chat", b'{"a": 1}', 5.0)])

    def test_get_sends_no_body(self) -> None:
        opener = FakeOpener(FakeResponse(200, b"{}"))
        ollama_transport(opener).request_json("GET", f"{BASE_URL}/api/tags", None, 5.0)
        self.assertIsNone(opener.requests[0][2])

    def test_server_down_raises_provider_request_error(self) -> None:
        error = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
        with self.assertRaises(ProviderRequestError) as raised:
            ollama_transport(FakeOpener(error=error)).request_json("GET", BASE_URL, None, 5.0)
        self.assertIn("No se pudo conectar", str(raised.exception))

    def test_http_500_raises_provider_request_error_with_the_detail(self) -> None:
        body = io.BytesIO(b'{"error": "model runner crashed"}')
        error = urllib.error.HTTPError(f"{BASE_URL}/api/chat", 500, "Internal", Message(), body)
        with self.assertRaises(ProviderRequestError) as raised:
            ollama_transport(FakeOpener(error=error)).request_json("POST", BASE_URL, {}, 5.0)
        self.assertIn("HTTP 500", str(raised.exception))
        self.assertIn("model runner crashed", str(raised.exception))

    def test_non_2xx_status_without_http_error_is_rejected(self) -> None:
        opener = FakeOpener(FakeResponse(503, b"{}"))
        with self.assertRaises(ProviderRequestError):
            ollama_transport(opener).request_json("GET", BASE_URL, None, 5.0)

    def test_timeouts_raise_provider_request_error(self) -> None:
        for error in (TimeoutError("timed out"), urllib.error.URLError(TimeoutError("x"))):
            with self.subTest(error=error):
                transport = ollama_transport(FakeOpener(error=error))
                with self.assertRaises(ProviderRequestError) as raised:
                    transport.request_json("POST", BASE_URL, {}, 7.0)
                self.assertIn("en 7 s", str(raised.exception))

    def test_invalid_json_from_ollama_raises_provider_request_error(self) -> None:
        for raw in (b"<html>no</html>", b"[1, 2]", b"\xff\xfe"):
            with self.subTest(raw=raw):
                transport = ollama_transport(FakeOpener(FakeResponse(200, raw)))
                with self.assertRaises(ProviderRequestError):
                    transport.request_json("GET", BASE_URL, None, 5.0)

    def test_rejects_urls_that_are_not_http_before_opening(self) -> None:
        opener = FakeOpener(FakeResponse(200, b"{}"))
        with self.assertRaises(ConfigError):
            ollama_transport(opener).request_json("GET", "file:///etc/hosts", None, 5.0)
        self.assertEqual(opener.requests, [])

    def test_default_opener_does_not_connect_when_the_network_is_blocked(self) -> None:
        refused = OSError("network disabled in tests")
        with mock.patch("socket.create_connection", side_effect=refused) as blocked:
            provider = OllamaProvider(SETTINGS)
            with self.assertRaises(ProviderUnavailableError):
                provider.ensure_available()
            with self.assertRaises(ProviderRequestError):
                provider.complete(REQUEST)
        self.assertEqual(blocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
