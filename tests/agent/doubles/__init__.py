"""Doubles of the worker: the API, Keycloak, LiveKit, the transcriber and time, all in
memory."""

from tests.agent.doubles.agilina_api import FakeAgilinaApi, ScriptedApi
from tests.agent.doubles.keycloak import FakeTokenEndpoint, FakeWorkerTokens
from tests.agent.doubles.livekit import FakeJobContext
from tests.agent.doubles.speech import ScriptedSynthesizer
from tests.agent.doubles.time import FakeMonotonicClock, RecordedSleep
from tests.agent.doubles.transcriber import FakeTranscriber

__all__ = [
    "FakeAgilinaApi",
    "FakeJobContext",
    "FakeMonotonicClock",
    "FakeTokenEndpoint",
    "FakeTranscriber",
    "FakeWorkerTokens",
    "RecordedSleep",
    "ScriptedApi",
    "ScriptedSynthesizer",
]
