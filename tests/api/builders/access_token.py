"""Builders of the access tokens Keycloak signs, and of the keys that sign them."""

import base64
import functools
import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Self

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.api.builders.defaults import NOW

ISSUER = "http://auth.test/realms/agilina"
AUDIENCE = "agilina-api"
SUBJECT = "6f1c7d2e-1b8a-4f6e-9a55-2f0f6b6f3a11"


@dataclass(frozen=True)
class SigningKey:
    """A realm key: signs tokens and publishes its public half (JWKS)."""

    key_id: str
    private_key: rsa.RSAPrivateKey

    def jwk(self) -> dict[str, Any]:
        """How Keycloak publishes it: a signing key with its ``kid``."""
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**public, "kid": self.key_id, "use": "sig", "alg": "RS256"}

    def public_pem(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


def signing_key(key_id: str = "key-1", variant: str = "") -> SigningKey:
    """A key per ``(key_id, variant)``, generated once: 2048-bit generation is slow.

    The same ``key_id`` with another ``variant`` is a different key under the same name,
    which is what a forged signature looks like."""
    return _generated(key_id, variant)


@functools.cache
def _generated(key_id: str, variant: str) -> SigningKey:
    # ``functools.cache`` keys on the arguments as written, so the defaults are applied above:
    # ``signing_key()`` and ``signing_key("key-1")`` must be the same key.
    return SigningKey(key_id, rsa.generate_private_key(public_exponent=65537, key_size=2048))


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass(frozen=True)
class AccessTokenBuilder:
    """A valid access token of Julián, issued by the realm at ``NOW`` for 15 minutes."""

    key: SigningKey = field(default_factory=signing_key)
    issuer: str = ISSUER
    audience: str | list[str] | None = AUDIENCE
    subject: str | None = SUBJECT
    token_type: str | None = "Bearer"  # noqa: S105 - the ``typ`` claim, not a secret
    issued_at: datetime = NOW
    lifetime: timedelta = timedelta(minutes=15)
    not_before: datetime | None = None
    extra_claims: dict[str, Any] = field(default_factory=dict)
    without_expiry: bool = False

    def signed_with(self, key: SigningKey) -> Self:
        return replace(self, key=key)

    def issued_by(self, issuer: str) -> Self:
        return replace(self, issuer=issuer)

    def for_audience(self, audience: str | list[str] | None) -> Self:
        return replace(self, audience=audience)

    def for_subject(self, subject: str | None) -> Self:
        return replace(self, subject=subject)

    def of_type(self, token_type: str | None) -> Self:
        return replace(self, token_type=token_type)

    def issued_at_instant(self, instant: datetime) -> Self:
        return replace(self, issued_at=instant)

    def valid_for(self, lifetime: timedelta) -> Self:
        return replace(self, lifetime=lifetime)

    def not_before_instant(self, instant: datetime) -> Self:
        return replace(self, not_before=instant)

    def never_expiring(self) -> Self:
        return replace(self, without_expiry=True)

    def with_claim(self, name: str, value: Any) -> Self:
        return replace(self, extra_claims={**self.extra_claims, name: value})

    def as_worker(self) -> Self:
        """The token the agent worker gets with its client credentials."""
        return self.with_claim("azp", "agilina-worker")

    def claims(self) -> dict[str, Any]:
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "iat": int(self.issued_at.timestamp()),
            "azp": "agilina-web",
        }
        if not self.without_expiry:
            claims["exp"] = int((self.issued_at + self.lifetime).timestamp())
        if self.audience is not None:
            claims["aud"] = self.audience
        if self.subject is not None:
            claims["sub"] = self.subject
        if self.token_type is not None:
            claims["typ"] = self.token_type
        if self.not_before is not None:
            claims["nbf"] = int(self.not_before.timestamp())
        return {**claims, **self.extra_claims}

    def build(self) -> str:
        return jwt.encode(
            self.claims(),
            self.key.private_key,
            algorithm="RS256",
            headers={"kid": self.key.key_id},
        )

    def build_unsigned(self) -> str:
        """The ``alg: none`` token an attacker would try: valid claims, no signature."""
        return jwt.encode(self.claims(), None, algorithm="none", headers={"kid": self.key.key_id})

    def build_hmac_with_the_public_key(self) -> str:
        """The classic downgrade: HS256 "signed" with the realm's public key as the secret.

        PyJWT refuses to make it, so it is assembled by hand."""
        header = _base64url(
            json.dumps({"alg": "HS256", "typ": "JWT", "kid": self.key.key_id}).encode()
        )
        payload = _base64url(json.dumps(self.claims()).encode())
        signature = hmac.new(
            self.key.public_pem(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        return f"{header}.{payload}.{_base64url(signature)}"
