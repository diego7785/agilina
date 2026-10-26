"""The transcription port, in memory: counts the calls instead of transcribing."""

from agilina_shared.enums import Language


class FakeTranscriber:
    def __init__(self) -> None:
        self.transcribed = 0
        self.availability_checks = 0

    async def transcribe(self, audio: bytes, language: Language) -> str:
        self.transcribed += 1
        return ""

    async def is_available(self) -> bool:
        self.availability_checks += 1
        return True
