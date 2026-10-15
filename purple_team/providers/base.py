"""Port to the language model and the values that cross it (no internal dependencies)."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RequestTrace:
    """Traceability metadata; real adapters only use it for logging."""

    run_id: str
    case_id: str


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """What the core sends to the model."""

    system_prompt: str
    user_content: str
    trace: RequestTrace
    temperature: float


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Raw text returned by the model and who produced it.

    ``thinking`` holds the separate reasoning trace of models with a thinking mode (``None``
    when the provider returns none); it is never mixed into ``text``.
    """

    text: str
    provider: str
    model: str
    thinking: str | None = None


class ProviderUnavailableError(RuntimeError):
    """The configured provider cannot be used (CLI exit code 2)."""


class ProviderRequestError(RuntimeError):
    """One call to the provider failed (network, timeout, HTTP status or invalid body).

    The runner records it as a per-case error and the run continues.
    """


@runtime_checkable
class ModelProvider(Protocol):
    """Access to a language model; the composition root chooses the implementation."""

    @property
    def name(self) -> str:
        """Provider name written to the records."""

    @property
    def model(self) -> str:
        """Model name written to the records."""

    def ensure_available(self) -> None:
        """Preflight check; raise ``ProviderUnavailableError`` when it cannot be used."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Send the request and return the raw response."""
