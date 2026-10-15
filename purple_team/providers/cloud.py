"""Cloud adapter: Gemini ``generateContent`` over REST with the shared stdlib transport.

The API key is never stored in files nor written to any record: the configuration only
names the environment variable that holds it (``api_key_env``), the key is read from the
``environ`` given to the CLI and it only travels in the ``x-goog-api-key`` header, never in
the URL. Every error message passes the key in ``redact`` so it is replaced by
``[REDACTED]`` even if a server echoed it back.
"""

import re
from collections.abc import Mapping
from typing import Final

from purple_team.config import CloudSettings, CloudThinkingLevel
from purple_team.errors import ConfigError
from purple_team.providers.base import (
    ModelRequest,
    ModelResponse,
    ProviderRequestError,
    ProviderUnavailableError,
)
from purple_team.providers.http_transport import (
    JsonTransport,
    UrllibTransport,
    redact_secrets,
    validate_http_url,
)

CLOUD_PROVIDER_NAME: Final = "cloud"
GEMINI_SERVICE: Final = "Gemini"
API_KEY_HEADER: Final = "x-goog-api-key"
MODELS_PATH: Final = "/models/"
GENERATE_SUFFIX: Final = ":generateContent"
MODEL_NAME_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")
SUPPORTED_VENDORS: Final = frozenset({"gemini"})
ALLOWED_SCHEMES: Final = frozenset({"https"})
JSON_MIME_TYPE: Final = "application/json"
GET: Final = "GET"
POST: Final = "POST"


class CloudProvider:
    """Adapter for a Gemini model; building it never reads the key nor opens a connection."""

    def __init__(
        self,
        settings: CloudSettings,
        environ: Mapping[str, str],
        transport: JsonTransport | None = None,
    ) -> None:
        if settings.vendor not in SUPPORTED_VENDORS:
            supported = ", ".join(sorted(SUPPORTED_VENDORS))
            message = f"Proveedor de nube no soportado: {settings.vendor}. Opciones: {supported}"
            raise ConfigError(message)
        if not MODEL_NAME_PATTERN.match(settings.model):
            message = f"Modelo de nube inválido: {settings.model!r} ({MODEL_NAME_PATTERN.pattern})"
            raise ConfigError(message)
        self._settings = settings
        self._base_url = validate_http_url(settings.base_url, ALLOWED_SCHEMES, GEMINI_SERVICE)
        self._environ = environ
        default_transport = UrllibTransport(GEMINI_SERVICE, ALLOWED_SCHEMES)
        self._transport: JsonTransport = transport if transport is not None else default_transport
        self._api_key: str | None = None

    @property
    def name(self) -> str:
        """Provider name written to the records."""
        return CLOUD_PROVIDER_NAME

    @property
    def model(self) -> str:
        """Configured model."""
        return self._settings.model

    def ensure_available(self) -> None:
        """Read the key from the environment and check the model with ``GET models/{model}``."""
        api_key = self._read_api_key()
        url = f"{self._base_url}{MODELS_PATH}{self._settings.model}"
        try:
            self._transport.request_json(
                GET,
                url,
                None,
                self._settings.timeout_seconds,
                headers={API_KEY_HEADER: api_key},
                redact=(api_key,),
            )
        except ProviderRequestError as exc:
            message = f"Gemini no está disponible o la llave/el modelo no son válidos: {exc}"
            raise ProviderUnavailableError(message) from exc
        self._api_key = api_key

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send one ``generateContent`` call; ``ProviderRequestError`` when it fails."""
        api_key = self._api_key if self._api_key is not None else self._read_api_key()
        url = f"{self._base_url}{MODELS_PATH}{self._settings.model}{GENERATE_SUFFIX}"
        body = self._transport.request_json(
            POST,
            url,
            build_generate_payload(request, self._settings),
            self._settings.timeout_seconds,
            headers={API_KEY_HEADER: api_key},
            redact=(api_key,),
        )
        try:
            text, thinking = parse_generate_response(body)
        except ValueError as exc:
            # The block and finish reasons come from the server: redact them too.
            raise ProviderRequestError(redact_secrets(str(exc), (api_key,))) from exc
        return ModelResponse(
            text=text,
            provider=CLOUD_PROVIDER_NAME,
            model=self._settings.model,
            thinking=thinking,
        )

    def _read_api_key(self) -> str:
        variable = self._settings.api_key_env
        api_key = self._environ.get(variable, "").strip()
        if not api_key:
            message = (
                f"Falta la llave de Gemini: exporta la variable {variable} "
                "(no la escribas en archivos)"
            )
            raise ProviderUnavailableError(message)
        return api_key


def build_generate_payload(request: ModelRequest, settings: CloudSettings) -> dict[str, object]:
    """Body of ``models/{model}:generateContent``; the temperature comes from the request.

    ``thinkingConfig.thinkingLevel`` is sent unless the level is ``default`` (model default).
    """
    generation_config: dict[str, object] = {
        "temperature": request.temperature,
        "responseMimeType": JSON_MIME_TYPE,
    }
    if settings.thinking_level is not CloudThinkingLevel.DEFAULT:
        generation_config["thinkingConfig"] = {"thinkingLevel": settings.thinking_level.value}
    return {
        "system_instruction": {"parts": [{"text": request.system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": request.user_content}]}],
        "generationConfig": generation_config,
    }


def parse_generate_response(body: Mapping[str, object]) -> tuple[str, str | None]:
    """Return the answer text and the reasoning (parts with ``thought: true``) or ``None``.

    Raise ``ValueError`` when the prompt was blocked or when there is no answer text.
    """
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        feedback = body.get("promptFeedback")
        reason = feedback.get("blockReason") if isinstance(feedback, Mapping) else None
        if reason is not None:
            raise ValueError(f"Gemini bloqueó la petición ({reason})")
        raise ValueError("La respuesta de Gemini no tiene una lista 'candidates' válida")
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        raise ValueError("La respuesta de Gemini no tiene un objeto 'candidates[0]'")
    texts: list[str] = []
    thoughts: list[str] = []
    for part in _parts(candidate):
        text = part.get("text")
        if not isinstance(text, str):
            continue
        if part.get("thought") is True:
            thoughts.append(text)
        else:
            texts.append(text)
    answer = "".join(texts)
    if not answer:
        finish_reason = candidate.get("finishReason")
        raise ValueError(f"Gemini no devolvió texto (finishReason={finish_reason})")
    return answer, "".join(thoughts) or None


def _parts(candidate: Mapping[str, object]) -> list[Mapping[str, object]]:
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, Mapping) else None
    if not isinstance(parts, list):
        return []
    return [part for part in parts if isinstance(part, Mapping)]
