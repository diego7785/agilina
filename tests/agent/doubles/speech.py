"""Speech double for the room job: a voice that fails for the sentences it is told to."""

from agilina_agent.application.errors import SpeechFailure, SpeechUnavailableError
from agilina_shared.enums import Language


class ScriptedSynthesizer:
    """Says each sentence unless its number (from 0) is in ``failing``: those raise as a
    voice service that does not answer."""

    def __init__(self, failing: set[int] | None = None) -> None:
        self.attempted: list[tuple[Language, str]] = []
        self._failing = failing or set()

    async def synthesize(self, text: str, language: Language) -> None:
        sentence = len(self.attempted)
        self.attempted.append((language, text))
        if sentence in self._failing:
            raise SpeechUnavailableError(SpeechFailure.PROVIDER_ERROR)
