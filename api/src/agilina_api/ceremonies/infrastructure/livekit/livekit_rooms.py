"""LiveKit implementation of the ``Rooms`` port.

Tokens are LiveKit access tokens: HS256 JWTs signed with the project's API secret, whose
``video`` claim says what the bearer may do. The room is created through LiveKit's Twirp
``RoomService/CreateRoom``, which is idempotent, with a short-lived token of its own.
"""

import logging
import time
from datetime import datetime

import httpx
import jwt

from agilina_api.ceremonies.application.errors import RoomServiceUnavailableError
from agilina_api.ceremonies.application.ports.outbound import Rooms

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0
ADMIN_TOKEN_SECONDS = 60
CREATE_ROOM_PATH = "/twirp/livekit.RoomService/CreateRoom"
# The clients connect over WebSocket; the server API answers on the same host over HTTP.
HTTP_SCHEMES = {"wss://": "https://", "ws://": "http://"}


class LiveKitRooms(Rooms):
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        api_secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------- port --
    async def open(self, room_name: str) -> None:
        url = self._server_url() + CREATE_ROOM_PATH
        admin_token = self._sign(
            {"exp": int(time.time()) + ADMIN_TOKEN_SECONDS, "video": {"roomCreate": True}}
        )
        try:
            response = await self._client.post(
                url, json={"name": room_name}, headers={"Authorization": f"Bearer {admin_token}"}
            )
        except httpx.HTTPError as error:
            logger.warning("LiveKit did not answer CreateRoom for room %s", room_name)
            raise RoomServiceUnavailableError(
                f"LiveKit did not answer ({type(error).__name__})"
            ) from error
        if not response.is_success:
            logger.warning(
                "LiveKit refused CreateRoom for room %s with status %s",
                room_name,
                response.status_code,
            )
            raise RoomServiceUnavailableError(
                f"LiveKit answered CreateRoom with status {response.status_code}"
            )
        logger.info("LiveKit opened room %s (status %s)", room_name, response.status_code)

    def admission_for(self, *, room_name: str, identity: str, expires_at: datetime) -> str:
        return self._sign(
            {
                "sub": identity,
                "exp": int(expires_at.timestamp()),
                "video": {
                    "room": room_name,
                    "roomJoin": True,
                    "canPublish": True,
                    "canPublishSources": ["microphone"],
                    "canSubscribe": True,
                    "canPublishData": False,  # LiveKit allows data unless told otherwise
                },
            }
        )

    # --------------------------------------------------------------- internals --
    def _sign(self, claims: dict[str, object]) -> str:
        """Fails closed: a token is never signed with missing credentials."""
        if not (self._url and self._api_key and self._api_secret):
            logger.warning("LiveKit is not configured: set the AGILINA_LIVEKIT_* variables")
            raise RoomServiceUnavailableError("LiveKit is not configured")
        return jwt.encode({"iss": self._api_key, **claims}, self._api_secret, algorithm="HS256")

    def _server_url(self) -> str:
        for socket_scheme, http_scheme in HTTP_SCHEMES.items():
            if self._url.startswith(socket_scheme):
                return http_scheme + self._url.removeprefix(socket_scheme)
        return self._url
