"""The LiveKit adapter against a simulated LiveKit (``httpx.MockTransport``).

It checks the token it signs and what it sends to open a room; no LiveKit server runs.
"""

import json
import logging
from datetime import UTC, datetime

import httpx
import jwt
import pytest

from agilina_api.ceremonies.application.errors import RoomServiceUnavailableError
from agilina_api.ceremonies.infrastructure.livekit.livekit_rooms import (
    REQUEST_TIMEOUT_SECONDS,
    LiveKitRooms,
)

API_KEY = "test-api-key"
API_SECRET = "a-test-secret-long-enough-for-hs256-0123"  # >= 32 bytes, as pyjwt asks
ROOM = "daily-7c2a"
IDENTITY = "a5b30f20-929f-413f-a767-c328958e9a65"
EXPIRES_AT = datetime(2026, 10, 18, 15, 30, tzinfo=UTC)


class FakeLiveKit:
    """Answers like LiveKit's RoomService and remembers what it was asked."""

    def __init__(self, *, status: int = 200, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, json={"name": json.loads(request.content)["name"]})

    def rooms(self, **overrides) -> LiveKitRooms:
        fields = {
            "url": "wss://livekit.example.test",
            "api_key": API_KEY,
            "api_secret": API_SECRET,
            "client": httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
        }
        return LiveKitRooms(**{**fields, **overrides})


def _decode(token: str) -> dict:
    return jwt.decode(token, API_SECRET, algorithms=["HS256"], options={"verify_exp": False})


def test_the_admission_lets_the_identity_join_only_that_room_until_the_clock_says():
    claims = _decode(
        FakeLiveKit()
        .rooms()
        .admission_for(room_name=ROOM, identity=IDENTITY, expires_at=EXPIRES_AT)
    )

    assert claims["iss"] == API_KEY
    assert claims["sub"] == IDENTITY
    assert claims["exp"] == int(EXPIRES_AT.timestamp())
    assert "name" not in claims
    assert claims["video"] == {
        "room": ROOM,
        "roomJoin": True,
        "canPublish": True,
        "canPublishSources": ["microphone"],
        "canSubscribe": True,
        "canPublishData": False,
    }


async def test_open_creates_the_room_over_https_with_a_room_create_token():
    livekit = FakeLiveKit()

    await livekit.rooms().open(ROOM)

    [request] = livekit.requests
    assert request.method == "POST"
    assert str(request.url) == "https://livekit.example.test/twirp/livekit.RoomService/CreateRoom"
    assert json.loads(request.content) == {"name": ROOM}
    scheme, token = request.headers["Authorization"].split(" ")
    assert scheme == "Bearer"
    claims = _decode(token)
    assert claims["iss"] == API_KEY
    assert claims["video"] == {"roomCreate": True}


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("ws://livekit:7880/", "http://livekit:7880"),
        ("https://livekit.example.test", "https://livekit.example.test"),
    ],
)
async def test_open_derives_the_server_url_from_the_configured_one(configured, expected):
    livekit = FakeLiveKit()

    await livekit.rooms(url=configured).open(ROOM)

    assert str(livekit.requests[0].url) == expected + "/twirp/livekit.RoomService/CreateRoom"


@pytest.mark.parametrize(
    "livekit",
    [
        FakeLiveKit(status=503),
        FakeLiveKit(status=401),
        FakeLiveKit(error=httpx.ConnectError("refused")),
        FakeLiveKit(error=httpx.ConnectTimeout("timed out")),
    ],
    ids=["5xx", "4xx", "network", "timeout"],
)
async def test_a_failing_room_server_is_unavailable(livekit):
    with pytest.raises(RoomServiceUnavailableError):
        await livekit.rooms().open(ROOM)


@pytest.mark.parametrize("missing", ["url", "api_key", "api_secret"])
async def test_missing_credentials_fail_closed_without_calling_the_server(missing, caplog):
    livekit = FakeLiveKit()
    rooms = livekit.rooms(**{missing: ""})

    with pytest.raises(RoomServiceUnavailableError):
        await rooms.open(ROOM)
    with pytest.raises(RoomServiceUnavailableError):
        rooms.admission_for(room_name=ROOM, identity=IDENTITY, expires_at=EXPIRES_AT)
    assert livekit.requests == []
    assert "LiveKit is not configured" in caplog.text


def _assert_logs_are_clean(caplog, livekit: FakeLiveKit, admission: str) -> None:
    admin_token = livekit.requests[0].headers["Authorization"].removeprefix("Bearer ")
    assert ROOM in caplog.text
    for secret in (API_SECRET, admission, admin_token):
        assert secret not in caplog.text


async def test_opening_a_room_logs_neither_tokens_nor_the_secret(caplog):
    livekit = FakeLiveKit()
    rooms = livekit.rooms()
    caplog.set_level(logging.DEBUG)

    admission = rooms.admission_for(room_name=ROOM, identity=IDENTITY, expires_at=EXPIRES_AT)
    await rooms.open(ROOM)

    _assert_logs_are_clean(caplog, livekit, admission)


async def test_a_refused_room_logs_neither_tokens_nor_the_secret(caplog):
    livekit = FakeLiveKit(status=503)
    rooms = livekit.rooms()
    caplog.set_level(logging.DEBUG)

    admission = rooms.admission_for(room_name=ROOM, identity=IDENTITY, expires_at=EXPIRES_AT)
    with pytest.raises(RoomServiceUnavailableError) as raised:
        await rooms.open(ROOM)

    _assert_logs_are_clean(caplog, livekit, admission)
    assert API_SECRET not in str(raised.value)


async def test_closing_the_adapter_closes_its_http_client():
    rooms = FakeLiveKit().rooms()

    await rooms.aclose()

    assert rooms._client.is_closed is True  # noqa: SLF001


async def test_without_a_client_it_builds_one_with_the_request_timeout():
    rooms = LiveKitRooms(url="wss://livekit.example.test", api_key=API_KEY, api_secret=API_SECRET)

    assert rooms._client.timeout == httpx.Timeout(REQUEST_TIMEOUT_SECONDS)  # noqa: SLF001
    await rooms.aclose()
