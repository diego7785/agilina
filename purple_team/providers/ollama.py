"""Adapter for a local Ollama server over the shared stdlib HTTP transport.

``ensure_available`` asks ``GET {base_url}/api/tags`` whether the configured model is
downloaded; ``complete`` sends ``POST {base_url}/api/chat`` with ``stream: false``. The
network itself lives in ``providers/http_transport.py`` (the only module that imports
``urllib``); ``base_url`` must be ``http`` or ``https`` and every failure of a call becomes
``ProviderRequestError``, recorded by the runner as a per-case error.
"""

from collections.abc import Mapping
from typing import Final

from purple_team.config import OllamaFormat, OllamaSettings
from purple_team.core.models import ceremony_output_json_schema
from purple_team.providers.base import (
    ModelRequest,
    ModelResponse,
    ProviderRequestError,
    ProviderUnavailableError,
)
from purple_team.providers.http_transport import JsonTransport, UrllibTransport, validate_http_url

OLLAMA_PROVIDER_NAME: Final = "ollama"
OLLAMA_SERVICE: Final = "Ollama"
CHAT_PATH: Final = "/api/chat"
TAGS_PATH: Final = "/api/tags"
ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
DEFAULT_TAG: Final = "latest"
GET: Final = "GET"
POST: Final = "POST"
MODEL_NAME_KEYS: Final = ("name", "model")


def validate_base_url(base_url: str) -> str:
    """Return ``base_url`` without a trailing ``/``; ``ConfigError`` unless http(s) + host."""
    return validate_http_url(base_url, ALLOWED_SCHEMES, OLLAMA_SERVICE)


class OllamaProvider:
    """Adapter for a local Ollama server."""

    def __init__(self, settings: OllamaSettings, transport: JsonTransport | None = None) -> None:
        self._settings = settings
        self._base_url = validate_base_url(settings.base_url)
        default_transport = UrllibTransport(OLLAMA_SERVICE, ALLOWED_SCHEMES)
        self._transport: JsonTransport = transport if transport is not None else default_transport

    @property
    def name(self) -> str:
        """Provider name written to the records."""
        return OLLAMA_PROVIDER_NAME

    @property
    def model(self) -> str:
        """Configured model."""
        return self._settings.model

    def ensure_available(self) -> None:
        """Check that the server answers and that the configured model is downloaded."""
        url = self._base_url + TAGS_PATH
        try:
            body = self._transport.request_json(GET, url, None, self._settings.timeout_seconds)
            installed = installed_models(body)
        except (ProviderRequestError, ValueError) as exc:
            message = (
                f"Ollama no está disponible en {self._base_url}: {exc}. Comprueba que el "
                "servidor esté en marcha (ollama serve)"
            )
            raise ProviderUnavailableError(message) from exc
        if not is_model_installed(self._settings.model, installed):
            shown = ", ".join(sorted(installed)) or "ninguno"
            message = (
                f"El modelo {self._settings.model} no está descargado en Ollama "
                f"({self._base_url}; modelos: {shown}). Descárgalo con: "
                f"ollama pull {self._settings.model}"
            )
            raise ProviderUnavailableError(message)

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send one chat request; raise ``ProviderRequestError`` when the call fails."""
        url = self._base_url + CHAT_PATH
        payload = build_chat_payload(request, self._settings)
        body = self._transport.request_json(POST, url, payload, self._settings.timeout_seconds)
        try:
            text = parse_chat_response(body)
            thinking = parse_chat_thinking(body)
        except ValueError as exc:
            raise ProviderRequestError(str(exc)) from exc
        return ModelResponse(
            text=text,
            provider=OLLAMA_PROVIDER_NAME,
            model=self._settings.model,
            thinking=thinking,
        )


def build_chat_payload(request: ModelRequest, settings: OllamaSettings) -> dict[str, object]:
    """Body of ``POST /api/chat``; the temperature comes from the request.

    ``think`` is always sent. ``format`` is ``"json"``, the JSON Schema of the closing
    (``schema``) or absent (``none``).
    """
    payload: dict[str, object] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_content},
        ],
        "stream": False,
        "think": settings.think,
        "options": {"temperature": request.temperature},
    }
    match settings.output_format:
        case OllamaFormat.JSON:
            payload["format"] = OllamaFormat.JSON.value
        case OllamaFormat.SCHEMA:
            payload["format"] = ceremony_output_json_schema()
        case OllamaFormat.NONE:
            pass
    return payload


def parse_chat_response(body: Mapping[str, object]) -> str:
    """Extract ``message.content`` from a ``/api/chat`` response body."""
    content = _message(body).get("content")
    if not isinstance(content, str):
        raise ValueError("La respuesta de Ollama no tiene el texto 'message.content'")
    return content


def parse_chat_thinking(body: Mapping[str, object]) -> str | None:
    """Extract ``message.thinking`` (``None`` when it is absent or empty)."""
    thinking = _message(body).get("thinking")
    if thinking is None or thinking == "":
        return None
    if not isinstance(thinking, str):
        raise ValueError("El campo 'message.thinking' de Ollama no es un texto")
    return thinking


def installed_models(body: Mapping[str, object]) -> frozenset[str]:
    """Names listed by ``GET /api/tags`` (``models[].name`` and ``models[].model``)."""
    models = body.get("models")
    if not isinstance(models, list):
        raise ValueError("la respuesta de /api/tags no tiene la lista 'models'")
    names: set[str] = set()
    for entry in models:
        if not isinstance(entry, Mapping):
            continue
        for key in MODEL_NAME_KEYS:
            value = entry.get(key)
            if isinstance(value, str):
                names.add(value)
    return frozenset(names)


def is_model_installed(model: str, installed: frozenset[str]) -> bool:
    """Exact match; a model without a tag also matches its ``:latest`` name."""
    candidates = {model} if ":" in model else {model, f"{model}:{DEFAULT_TAG}"}
    return bool(candidates & installed)


def _message(body: Mapping[str, object]) -> Mapping[str, object]:
    message = body.get("message")
    if not isinstance(message, Mapping):
        raise ValueError("La respuesta de Ollama no tiene el objeto 'message'")
    return message
