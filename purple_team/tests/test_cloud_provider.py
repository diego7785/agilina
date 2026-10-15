"""Tests for the Gemini adapter; no test opens a connection and the key is synthetic.

The provider is exercised with a fake ``JsonTransport`` and the redaction of the key with
the real ``UrllibTransport`` over a fake opener.
"""

import io
import unittest
import urllib.error
from collections.abc import Mapping, Sequence
from dataclasses import replace
from email.message import Message
from typing import Self

from purple_team.config import CloudSettings, CloudThinkingLevel
from purple_team.errors import ConfigError
from purple_team.providers.base import (
    ModelProvider,
    ModelRequest,
    ProviderRequestError,
    ProviderUnavailableError,
    RequestTrace,
)
from purple_team.providers.cloud import (
    ALLOWED_SCHEMES,
    API_KEY_HEADER,
    GEMINI_SERVICE,
    CloudProvider,
    build_generate_payload,
    parse_generate_response,
)
from purple_team.providers.http_transport import NO_HEADERS, REDACTED, UrllibTransport

FAKE_KEY = "clave-falsa-de-prueba"
KEY_VARIABLE = "PTH_CLOUD_API_KEY"
ENVIRON = {KEY_VARIABLE: FAKE_KEY}
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-3.8-flash"
TIMEOUT = 30.0
SETTINGS = CloudSettings(
    vendor="gemini",
    base_url=BASE_URL,
    model=MODEL,
    api_key_env=KEY_VARIABLE,
    timeout_seconds=TIMEOUT,
    temperature=1.0,
    thinking_level=CloudThinkingLevel.LOW,
)
REQUEST = ModelRequest(
    system_prompt="Eres Agilina.",
    user_content="<transcripcion>...</transcripcion>",
    trace=RequestTrace(run_id="run-1", case_id="c00-control"),
    temperature=0.4,
)
MODEL_BODY = {"name": f"models/{MODEL}"}


def answer(*parts: Mapping[str, object]) -> dict[str, object]:
    """A ``generateContent`` body with one candidate made of ``parts``."""
    return {"candidates": [{"content": {"parts": list(parts)}, "finishReason": "STOP"}]}


class FakeTransport:
    """Records every call; answers the scripted bodies in order or raises a fixed error."""

    def __init__(
        self,
        bodies: Sequence[Mapping[str, object]] = (),
        error: Exception | None = None,
    ) -> None:
        self._bodies = list(bodies)
        self.error = error
        self.calls: list[dict[str, object]] = []

    def request_json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        timeout: float,
        headers: Mapping[str, str] = NO_HEADERS,
        redact: Sequence[str] = (),
    ) -> Mapping[str, object]:
        call = {
            "method": method,
            "url": url,
            "payload": payload,
            "timeout": timeout,
            "headers": dict(headers),
            "redact": tuple(redact),
        }
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        return self._bodies.pop(0)


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


class RaisingOpener:
    """Opener that never touches the network: it always raises the given error."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.headers: list[dict[str, str]] = []

    def open(self, request: object, *, timeout: float) -> FakeResponse:
        self.headers.append(dict(getattr(request, "headers", {})))
        raise self.error


def provider_with(transport: FakeTransport, environ: Mapping[str, str] = ENVIRON) -> CloudProvider:
    return CloudProvider(SETTINGS, environ, transport)


class EnsureAvailableTest(unittest.TestCase):
    def test_missing_key_is_unavailable_and_names_the_variable(self) -> None:
        transport = FakeTransport()
        with self.assertRaises(ProviderUnavailableError) as raised:
            provider_with(transport, environ={}).ensure_available()
        self.assertIn(KEY_VARIABLE, str(raised.exception))
        self.assertEqual(transport.calls, [])

    def test_checks_the_model_with_the_key_only_in_the_header(self) -> None:
        transport = FakeTransport([MODEL_BODY])
        provider = provider_with(transport)
        self.assertIsInstance(provider, ModelProvider)
        provider.ensure_available()
        call = transport.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], f"{BASE_URL}/models/{MODEL}")
        self.assertNotIn(FAKE_KEY, str(call["url"]))
        self.assertEqual(call["headers"], {API_KEY_HEADER: FAKE_KEY})
        self.assertEqual(call["redact"], (FAKE_KEY,))
        self.assertEqual(call["timeout"], TIMEOUT)

    def test_request_failure_is_unavailable(self) -> None:
        transport = FakeTransport(error=ProviderRequestError("Gemini respondió HTTP 404"))
        with self.assertRaises(ProviderUnavailableError) as raised:
            provider_with(transport).ensure_available()
        self.assertIn("HTTP 404", str(raised.exception))

    def test_repr_never_shows_the_key(self) -> None:
        provider = provider_with(FakeTransport([MODEL_BODY]))
        provider.ensure_available()
        self.assertNotIn(FAKE_KEY, repr(provider))


class CompleteTest(unittest.TestCase):
    def test_posts_generate_content_and_returns_the_text(self) -> None:
        transport = FakeTransport([MODEL_BODY, answer({"text": '{"summary": "x"}'})])
        provider = provider_with(transport)
        provider.ensure_available()
        response = provider.complete(REQUEST)
        self.assertEqual(response.text, '{"summary": "x"}')
        self.assertIsNone(response.thinking)
        self.assertEqual((response.provider, response.model), ("cloud", MODEL))
        call = transport.calls[1]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], f"{BASE_URL}/models/{MODEL}:generateContent")
        self.assertEqual(call["payload"], build_generate_payload(REQUEST, SETTINGS))
        self.assertEqual(call["headers"], {API_KEY_HEADER: FAKE_KEY})
        self.assertEqual(call["redact"], (FAKE_KEY,))

    def test_complete_without_preflight_reads_the_key(self) -> None:
        transport = FakeTransport([answer({"text": "{}"})])
        self.assertEqual(provider_with(transport).complete(REQUEST).text, "{}")
        self.assertEqual(transport.calls[0]["headers"], {API_KEY_HEADER: FAKE_KEY})

    def test_thought_parts_go_to_thinking(self) -> None:
        body = answer({"text": "pienso", "thought": True}, {"text": "{}"})
        response = provider_with(FakeTransport([body])).complete(REQUEST)
        self.assertEqual((response.text, response.thinking), ("{}", "pienso"))

    def test_blocked_prompt_and_empty_text_are_request_errors(self) -> None:
        blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
        empty = answer({"text": "solo razono", "thought": True})
        for body, message in ((blocked, "SAFETY"), (empty, "no devolvió texto")):
            with self.subTest(message=message):
                with self.assertRaises(ProviderRequestError) as raised:
                    provider_with(FakeTransport([body])).complete(REQUEST)
                self.assertIn(message, str(raised.exception))

    def test_transport_failure_propagates_as_request_error(self) -> None:
        transport = FakeTransport(error=ProviderRequestError("timeout"))
        with self.assertRaises(ProviderRequestError):
            provider_with(transport).complete(REQUEST)


class PayloadTest(unittest.TestCase):
    def test_payload_uses_the_request_temperature_and_the_thinking_level(self) -> None:
        expected = {
            "system_instruction": {"parts": [{"text": "Eres Agilina."}]},
            "contents": [
                {"role": "user", "parts": [{"text": "<transcripcion>...</transcripcion>"}]},
            ],
            "generationConfig": {
                "temperature": 0.4,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        self.assertEqual(build_generate_payload(REQUEST, SETTINGS), expected)

    def test_default_thinking_level_sends_no_thinking_config(self) -> None:
        settings = replace(SETTINGS, thinking_level=CloudThinkingLevel.DEFAULT)
        config = build_generate_payload(REQUEST, settings)["generationConfig"]
        self.assertEqual(config, {"temperature": 0.4, "responseMimeType": "application/json"})

    def test_rejects_malformed_generate_responses(self) -> None:
        bodies: list[dict[str, object]] = [
            {},
            {"candidates": []},
            {"candidates": ["x"]},
            {"candidates": [{"content": "x"}]},
            {"candidates": [{"content": {"parts": [{"text": 1}]}}]},
        ]
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    parse_generate_response(body)


class ConfigurationTest(unittest.TestCase):
    def test_rejects_vendor_base_url_and_model_that_are_not_valid(self) -> None:
        invalid = [
            replace(SETTINGS, vendor="acme"),
            replace(SETTINGS, base_url="http://generativelanguage.googleapis.com/v1beta"),
            replace(SETTINGS, base_url="file:///etc/hosts"),
            replace(SETTINGS, model="../x"),
            replace(SETTINGS, model="gemini 3"),
        ]
        for settings in invalid:
            with self.subTest(settings=settings):
                with self.assertRaises(ConfigError):
                    CloudProvider(settings, ENVIRON, FakeTransport())


class RedactionTest(unittest.TestCase):
    def transport(self, error: Exception) -> tuple[UrllibTransport, RaisingOpener]:
        opener = RaisingOpener(error)
        return UrllibTransport(GEMINI_SERVICE, ALLOWED_SCHEMES, opener), opener

    def test_the_key_echoed_in_an_http_error_body_is_redacted(self) -> None:
        body = io.BytesIO(f'{{"error": {{"message": "API key {FAKE_KEY} not valid"}}}}'.encode())
        error = urllib.error.HTTPError(BASE_URL, 400, "Bad Request", Message(), body)
        transport, opener = self.transport(error)
        provider = CloudProvider(SETTINGS, ENVIRON, transport)
        with self.assertRaises(ProviderUnavailableError) as raised:
            provider.ensure_available()
        message = str(raised.exception)
        self.assertNotIn(FAKE_KEY, message)
        self.assertIn(REDACTED, message)
        self.assertIn("HTTP 400", message)
        self.assertEqual(opener.headers[0][API_KEY_HEADER.capitalize()], FAKE_KEY)

    def test_the_key_in_a_connection_error_is_redacted(self) -> None:
        transport, _opener = self.transport(urllib.error.URLError(f"refused {FAKE_KEY}"))
        with self.assertRaises(ProviderRequestError) as raised:
            CloudProvider(SETTINGS, ENVIRON, transport).complete(REQUEST)
        self.assertNotIn(FAKE_KEY, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
