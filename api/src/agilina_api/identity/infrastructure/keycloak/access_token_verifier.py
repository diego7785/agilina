"""Validation of the access tokens that Keycloak issues (HU-03).

A token is trusted only after all of this holds, and a failure of any kind is an answer
(``None``), never an exception: a bad token is expected input, not an error of the API.

- it is signed with RS256 by a key of the realm, found by its ``kid`` in the realm's key set
  (JWKS). Any other algorithm, ``none`` included, is refused before a key is even looked up;
- its issuer is the realm's public URL and its audience is this API (``agilina-api``);
- it is an access token (``typ: Bearer``), not an ID or a refresh token;
- it is neither expired nor from the future, with a small margin for clock drift. Time comes
  from the ``Clock`` port, like every other time rule of the system.

The realm's keys are read once and kept. A token with an unknown ``kid`` means that Keycloak
may have rotated its keys, so the key set is read again, but at most once in a while: a
caller who sends random ``kid`` values cannot make the API hammer Keycloak.

The token itself is never logged, only the reason it was refused.
"""

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt

from agilina_api.shared.application.ports import Clock

logger = logging.getLogger(__name__)

ALGORITHM = "RS256"
ACCESS_TOKEN_TYPE = "Bearer"  # noqa: S105 - the value of the ``typ`` claim, not a secret
LEEWAY = timedelta(seconds=30)
KEY_REFRESH_INTERVAL = timedelta(seconds=30)
REQUIRED_CLAIMS = ["exp", "iss", "aud", "sub"]


class KeycloakAccessTokenVerifier:
    def __init__(  # noqa: PLR0913
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        clock: Clock,
        client: httpx.AsyncClient | None = None,
        leeway: timedelta = LEEWAY,
        key_refresh_interval: timedelta = KEY_REFRESH_INTERVAL,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._clock = clock
        self._client = client or httpx.AsyncClient(timeout=5.0)
        self._leeway = leeway
        self._key_refresh_interval = key_refresh_interval
        self._keys: dict[str, jwt.PyJWK] = {}
        self._keys_read_at: datetime | None = None
        self._keys_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def verified_subject(self, token: str) -> str | None:
        """The ``sub`` of a valid access token, or ``None`` if it is not one."""
        claims = await self.verified_claims(token)
        return None if claims is None else str(claims["sub"])

    async def verified_claims(self, token: str) -> Mapping[str, Any] | None:
        """Every claim of a valid access token, or ``None`` if it is not one. Its ``sub`` is
        a non-blank string."""
        reason, claims = await self._verify(token)
        if reason is not None:
            logger.info("Access token rejected: %s", reason)
        return claims

    # --------------------------------------------------------------- internals --
    async def _verify(self, token: str) -> tuple[str | None, dict[str, Any] | None]:
        """``(reason, None)`` when refused and ``(None, claims)`` when valid."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            return "malformed", None
        if header.get("alg") != ALGORITHM:
            return "algorithm", None
        key_id = header.get("kid")
        if not isinstance(key_id, str):
            return "no_key_id", None
        key = await self._key(key_id)
        if key is None:
            return "unknown_key", None

        try:
            claims = self._decode(token, key)
        except jwt.InvalidSignatureError:
            return "signature", None
        except jwt.InvalidIssuerError:
            return "issuer", None
        except jwt.InvalidAudienceError:
            return "audience", None
        except jwt.MissingRequiredClaimError:
            return "missing_claim", None
        except jwt.PyJWTError:
            return "invalid", None

        reason = self._time_or_type_problem(claims)
        if reason is not None:
            return reason, None
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject.strip():
            return "no_subject", None
        return None, claims

    def _decode(self, token: str, key: jwt.PyJWK) -> dict[str, Any]:
        # The time claims are checked below with the Clock, not with the system clock.
        return jwt.decode(
            token,
            key.key,
            algorithms=[ALGORITHM],
            issuer=self._issuer,
            audience=self._audience,
            options={
                "require": REQUIRED_CLAIMS,
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )

    def _time_or_type_problem(self, claims: dict[str, Any]) -> str | None:
        if claims.get("typ") != ACCESS_TOKEN_TYPE:
            return "not_an_access_token"
        now = self._clock.now()
        expires_at = _instant(claims["exp"])
        if expires_at is None or now >= expires_at + self._leeway:
            return "expired"
        not_before = claims.get("nbf")
        if not_before is not None:
            starts_at = _instant(not_before)
            if starts_at is None or starts_at - self._leeway > now:
                return "not_yet_valid"
        return None

    async def _key(self, key_id: str) -> jwt.PyJWK | None:
        if key_id not in self._keys:
            await self._read_keys_if_allowed()
        return self._keys.get(key_id)

    async def _read_keys_if_allowed(self) -> None:
        async with self._keys_lock:
            now = self._clock.now()
            if (
                self._keys_read_at is not None
                and now - self._keys_read_at < self._key_refresh_interval
            ):
                return
            # Even a failed read counts: a Keycloak that is down is not asked again at once.
            self._keys_read_at = now
            keys = await self._download_keys()
            if keys is not None:
                self._keys = keys

    async def _download_keys(self) -> dict[str, jwt.PyJWK] | None:
        try:
            response = await self._client.get(self._jwks_url)
            if response.status_code != httpx.codes.OK:
                logger.error("The realm's keys could not be read: HTTP %s", response.status_code)
                return None
            published = response.json()["keys"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            logger.error("The realm's keys could not be read (%s)", type(error).__name__)
            return None

        keys: dict[str, jwt.PyJWK] = {}
        for published_key in published:
            # The realm also publishes an encryption key; only signing keys matter here.
            if not isinstance(published_key, dict) or published_key.get("use", "sig") != "sig":
                continue
            try:
                key = jwt.PyJWK.from_dict(published_key)
            except jwt.PyJWTError:
                continue
            if key.key_id is not None:
                keys[key.key_id] = key
        return keys


def _instant(seconds: object) -> datetime | None:
    """A numeric date claim as an aware UTC instant, or ``None`` when it is not a number."""
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None
