"""Worker ports.

The facilitation logic knows no SDK: it talks to these protocols and each
adapter is the only place in the code that knows a provider. Switching
transcription or synthesis means replacing an adapter, not touching the
facilitation machine.
"""

from typing import Protocol, runtime_checkable
from uuid import UUID

from agilina_shared.contract import CeremonyContext, CeremonyResult
from agilina_shared.enums import Language


@runtime_checkable
class Transcriber(Protocol):
    """Turns audio segments into text. It does not identify speakers: the
    identity arrives with the audio track."""

    async def transcribe(self, audio: bytes, language: Language) -> str: ...

    async def is_available(self) -> bool:
        """If it answers no, the ceremony goes on in degraded mode."""
        ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Turns the text of a template into audio to publish it in the room."""

    async def synthesize(self, text: str, language: Language) -> bytes: ...


@runtime_checkable
class AgilinaApi(Protocol):
    """The only two operations of the worker against the API, always within a tenant."""

    async def get_context(self, tenant: str, ceremony_id: UUID) -> CeremonyContext:
        """One request, no retry: raises ``ContextUnavailableError`` on any failure."""
        ...

    async def deliver_result(self, tenant: str, result: CeremonyResult) -> None:
        """Keeps the result on disk and retries until the API accepts it."""
        ...
