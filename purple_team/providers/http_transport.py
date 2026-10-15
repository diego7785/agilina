"""JSON over HTTP with ``urllib.request`` (stdlib only), shared by the Ollama and Gemini adapters.

This is the only module of the harness that may open a network connection. Every URL is
validated before opening (scheme in the allowed set and a host: bandit S310), proxies
from the environment are ignored and redirections are never followed: ``urllib`` would
resend the credential headers (``x-goog-api-key``) to the new location, so a 3xx answer is a
``ProviderRequestError``. Every failure of a single call (network, timeout, HTTP
status outside 2xx, body that is not a JSON object) becomes ``ProviderRequestError``, so the
runner records it as a per-case error and the run continues. Values listed in ``redact``
(the cloud API key) are replaced by ``[REDACTED]`` in every error message.
"""

import json
import types
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Final, Protocol, Self
from urllib.parse import urlsplit

from purple_team.errors import ConfigError
from purple_team.providers.base import ProviderRequestError

JSON_CONTENT_TYPE: Final = "application/json"
ENCODING: Final = "utf-8"
HTTP_OK_MIN: Final = 200
HTTP_OK_MAX: Final = 299
HTTP_REDIRECT_MIN: Final = 300
HTTP_REDIRECT_MAX: Final = 399
ERROR_DETAIL_MAX_CHARS: Final = 300
REDACTED: Final = "[REDACTED]"
NO_HEADERS: Final[Mapping[str, str]] = types.MappingProxyType({})


class HttpResponse(Protocol):
    """The part of ``http.client.HTTPResponse`` the transport uses."""

    @property
    def status(self) -> int:
        """HTTP status code."""

    def read(self) -> bytes:
        """Whole response body."""

    def __enter__(self) -> Self:
        """Context manager entry."""

    def __exit__(self, *exc_info: object) -> None:
        """Context manager exit (closes the response)."""


class Opener(Protocol):
    """The part of ``urllib.request.OpenerDirector`` the transport uses (tests fake it)."""

    def open(self, request: urllib.request.Request, *, timeout: float) -> HttpResponse:
        """Send the request and return the response."""


class JsonTransport(Protocol):
    """Sends one JSON request and returns the decoded JSON object of the answer."""

    def request_json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        timeout: float,
        headers: Mapping[str, str] = NO_HEADERS,
        redact: Sequence[str] = (),
    ) -> Mapping[str, object]:
        """Return the JSON body; raise ``ProviderRequestError`` on any failure."""


def validate_http_url(url: str, schemes: frozenset[str], service: str) -> str:
    """Return ``url`` without a trailing ``/``; ``ConfigError`` unless allowed scheme + host."""
    parts = urlsplit(url)
    if parts.scheme.casefold() not in schemes or not parts.netloc:
        allowed = " o ".join(f"{scheme}://" for scheme in sorted(schemes))
        message = f"URL de {service} inválida: {url!r}. Se esperaba una URL {allowed} con servidor"
        raise ConfigError(message)
    return url.rstrip("/")


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuses every redirection, so no header (the API key) is ever sent to another URL."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Never build the follow-up request; ``urllib`` then raises ``HTTPError(3xx)``."""
        return None


def build_opener() -> urllib.request.OpenerDirector:
    """Default opener without proxies nor redirections (building it opens no connection)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirectHandler())


def redact_secrets(message: str, secrets: Sequence[str]) -> str:
    """Replace every non-empty secret of ``secrets`` by ``[REDACTED]``."""
    for secret in secrets:
        if secret:
            message = message.replace(secret, REDACTED)
    return message


class UrllibTransport:
    """``JsonTransport`` over ``urllib.request``; the opener is injectable for the tests."""

    def __init__(self, service: str, schemes: frozenset[str], opener: Opener | None = None) -> None:
        self._service = service
        self._schemes = schemes
        self._opener: Opener = opener if opener is not None else build_opener()

    def request_json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        timeout: float,
        headers: Mapping[str, str] = NO_HEADERS,
        redact: Sequence[str] = (),
    ) -> Mapping[str, object]:
        """Send the request and decode the JSON object of the answer."""
        checked_url = validate_http_url(url, self._schemes, self._service)
        data = None if payload is None else json.dumps(payload).encode(ENCODING)
        all_headers = {"Accept": JSON_CONTENT_TYPE, "Content-Type": JSON_CONTENT_TYPE, **headers}
        # S310 is safe here: validate_http_url() above only lets the allowed schemes through.
        request = urllib.request.Request(  # noqa: S310
            checked_url,
            data=data,
            headers=all_headers,
            method=method,
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                status = response.status
                raw_body = response.read()
        except urllib.error.HTTPError as exc:
            if HTTP_REDIRECT_MIN <= exc.code <= HTTP_REDIRECT_MAX:
                message = self._redirect_message(exc.code, method, checked_url)
                raise ProviderRequestError(redact_secrets(message, redact)) from exc
            detail = _http_error_detail(exc)
            where = f"{method} {checked_url}"
            message = f"{self._service} respondió HTTP {exc.code} a {where}: {detail}"
            raise ProviderRequestError(redact_secrets(message, redact)) from exc
        except OSError as exc:  # URLError, TimeoutError, connection refused or reset
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if isinstance(reason, TimeoutError):
                message = f"{self._service} no respondió a {method} {checked_url} en {timeout:g} s"
            else:
                message = f"No se pudo conectar con {self._service} en {checked_url}: {reason}"
            raise ProviderRequestError(redact_secrets(message, redact)) from exc
        if HTTP_REDIRECT_MIN <= status <= HTTP_REDIRECT_MAX:
            message = self._redirect_message(status, method, checked_url)
            raise ProviderRequestError(redact_secrets(message, redact))
        if not HTTP_OK_MIN <= status <= HTTP_OK_MAX:
            message = f"{self._service} respondió HTTP {status} a {method} {checked_url}"
            raise ProviderRequestError(redact_secrets(message, redact))
        return self._decode_json_object(raw_body, checked_url)

    def _redirect_message(self, code: int, method: str, url: str) -> str:
        return (
            f"{self._service} respondió con una redirección HTTP {code} a {method} {url}. "
            "El banco no sigue redirecciones para no reenviar credenciales; revisa base_url"
        )

    def _decode_json_object(self, raw_body: bytes, url: str) -> Mapping[str, object]:
        try:
            data = json.loads(raw_body.decode(ENCODING))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            message = f"{self._service} devolvió un cuerpo que no es JSON ({url})"
            raise ProviderRequestError(message) from exc
        if not isinstance(data, dict):
            message = f"{self._service} devolvió un JSON que no es un objeto ({url})"
            raise ProviderRequestError(message)
        return data


def _http_error_detail(error: urllib.error.HTTPError) -> str:
    """Short text of an HTTP error body (Ollama: ``{"error": "..."}``; Gemini: nested)."""
    try:
        raw = error.read()
    except OSError:
        return str(error.reason)
    text = raw.decode(ENCODING, errors="replace").strip()
    return text[:ERROR_DETAIL_MAX_CHARS] or str(error.reason)
