"""Deterministic scripted provider: it never calls any service.

Each case has a benign answer and, when it carries an injection, a compromised answer.
The ``case_id`` of the trace only selects the script of the case; the decision between
both answers depends exclusively on the content that reaches the model: the compromised
answer is returned only when the injected text survived until ``user_content``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from purple_team.core.text import normalize_for_match
from purple_team.providers.base import ModelRequest, ModelResponse

MOCK_PROVIDER_NAME: Final = "mock"
MOCK_MODEL_NAME: Final = "mock-scripted-v1"


@dataclass(frozen=True, slots=True)
class MockScript:
    """Scripted answers of one case; ``trigger`` is the injection payload."""

    benign_response: str
    injected_response: str | None
    trigger: str | None


class MockFixtureError(LookupError):
    """There is no script for the requested case."""


class MockProvider:
    """Pure function of the request: no clock, no randomness, no files, no network."""

    def __init__(self, scripts: Mapping[str, MockScript]) -> None:
        self._scripts = dict(scripts)

    @property
    def name(self) -> str:
        """Provider name written to the records."""
        return MOCK_PROVIDER_NAME

    @property
    def model(self) -> str:
        """Model name written to the records."""
        return MOCK_MODEL_NAME

    def ensure_available(self) -> None:
        """The mock is always available."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Return the compromised answer only if the trigger reached the model."""
        script = self._scripts.get(request.trace.case_id)
        if script is None:
            message = f"No hay guion del mock para el caso {request.trace.case_id}"
            raise MockFixtureError(message)
        text = script.benign_response
        if script.trigger is not None and script.injected_response is not None:
            if normalize_for_match(script.trigger) in normalize_for_match(request.user_content):
                text = script.injected_response
        return ModelResponse(text=text, provider=MOCK_PROVIDER_NAME, model=MOCK_MODEL_NAME)
