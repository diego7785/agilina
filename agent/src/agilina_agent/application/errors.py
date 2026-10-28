"""Errors of the worker ports."""

from enum import StrEnum


class ContextUnavailableError(Exception):
    """The API did not hand over the ceremony context: without it there is no facilitation."""


class SpeechFailure(StrEnum):
    """Why a sentence was not heard. It goes to the log, never to the room."""

    INVALID_KEY = "invalid_key"
    QUOTA_OR_RATE_LIMIT = "quota_or_rate_limit"
    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"


class SpeechUnavailableError(Exception):
    """The voice service did not say the sentence: the room shows it as text instead."""

    def __init__(self, reason: SpeechFailure) -> None:
        super().__init__(reason.value)
        self.reason = reason
