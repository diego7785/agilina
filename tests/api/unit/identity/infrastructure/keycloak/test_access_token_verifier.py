"""The validation of Keycloak access tokens: what makes a token trustworthy, and every way it
can fail. The realm's keys are simulated; the signatures are real."""

import logging
from datetime import timedelta

import pytest

from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from tests.api.builders import (
    AUDIENCE,
    ISSUER,
    NOW,
    SUBJECT,
    AccessTokenBuilder,
    signing_key,
)
from tests.api.doubles import JWKS_URL, FakeClock, FakeRealmKeys

KEY = signing_key("key-1")


class Setup:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.realm = FakeRealmKeys(KEY)
        self.verifier = KeycloakAccessTokenVerifier(
            jwks_url=JWKS_URL,
            issuer=ISSUER,
            audience=AUDIENCE,
            clock=self.clock,
            client=self.realm.client(),
        )

    async def subject_of(self, token: str) -> str | None:
        return await self.verifier.verified_subject(token)


@pytest.fixture
def setup() -> Setup:
    return Setup()


# ------------------------------------------------------------------- a good token --
async def test_a_valid_token_gives_its_subject(setup):
    assert await setup.subject_of(AccessTokenBuilder().build()) == SUBJECT


async def test_the_audience_may_be_one_of_several(setup):
    token = AccessTokenBuilder().for_audience(["account", AUDIENCE]).build()

    assert await setup.subject_of(token) == SUBJECT


async def test_the_keys_are_read_once_and_kept(setup):
    await setup.subject_of(AccessTokenBuilder().build())
    await setup.subject_of(AccessTokenBuilder().build())

    assert setup.realm.reads == 1


async def test_the_claims_of_a_valid_token_are_all_given(setup):
    token = AccessTokenBuilder().as_worker().with_claim("custom", 7).build()

    claims = await setup.verifier.verified_claims(token)

    assert claims is not None
    assert claims["sub"] == SUBJECT and claims["iss"] == ISSUER
    assert claims["azp"] == "agilina-worker" and claims["custom"] == 7


@pytest.mark.parametrize(
    "token",
    [
        "not-a-token",
        AccessTokenBuilder().build_unsigned(),
        AccessTokenBuilder().issued_by("http://evil.test/realms/agilina").build(),
        AccessTokenBuilder().for_audience("account").build(),
        AccessTokenBuilder().of_type("Refresh").build(),
        AccessTokenBuilder().for_subject("  ").build(),
        AccessTokenBuilder().never_expiring().build(),
        AccessTokenBuilder().signed_with(signing_key("key-1", "attacker")).build(),
    ],
    ids=["garbage", "unsigned", "issuer", "audience", "type", "subject", "expiry", "signature"],
)
async def test_a_refused_token_gives_no_claims_and_the_reason_is_logged(setup, caplog, token):
    with caplog.at_level(logging.INFO):
        assert await setup.verifier.verified_claims(token) is None

    assert "Access token rejected" in caplog.text


# ------------------------------------------------------------------------ the time --
async def test_a_token_lives_until_its_expiry_plus_the_margin(setup):
    token = AccessTokenBuilder().build()  # expires 15 minutes after NOW

    setup.clock.current = NOW + timedelta(minutes=15, seconds=29)
    assert await setup.subject_of(token) == SUBJECT

    setup.clock.current = NOW + timedelta(minutes=15, seconds=30)
    assert await setup.subject_of(token) is None


async def test_an_expired_token_is_refused(setup):
    token = AccessTokenBuilder().issued_at_instant(NOW - timedelta(hours=1)).build()

    assert await setup.subject_of(token) is None


async def test_a_token_that_is_not_valid_yet_is_refused_unless_within_the_margin(setup):
    assert (
        await setup.subject_of(
            AccessTokenBuilder().not_before_instant(NOW + timedelta(seconds=29)).build()
        )
        == SUBJECT
    )
    assert (
        await setup.subject_of(
            AccessTokenBuilder().not_before_instant(NOW + timedelta(seconds=31)).build()
        )
        is None
    )


@pytest.mark.parametrize("claim", ["exp", "nbf"])
async def test_a_time_claim_that_is_not_a_date_is_refused(setup, claim):
    token = AccessTokenBuilder().with_claim(claim, "tomorrow").build()

    assert await setup.subject_of(token) is None


async def test_a_date_beyond_the_calendar_is_refused(setup):
    token = AccessTokenBuilder().with_claim("exp", 10**18).build()

    assert await setup.subject_of(token) is None


async def test_a_token_without_expiry_is_refused(setup):
    assert await setup.subject_of(AccessTokenBuilder().never_expiring().build()) is None


# ---------------------------------------------------------- who signed it and for whom --
async def test_a_signature_from_another_key_under_the_same_name_is_refused(setup):
    forged = AccessTokenBuilder().signed_with(signing_key("key-1", "attacker")).build()

    assert await setup.subject_of(forged) is None


async def test_a_token_without_signature_is_refused(setup):
    assert await setup.subject_of(AccessTokenBuilder().build_unsigned()) is None


async def test_a_token_signed_with_the_public_key_as_a_secret_is_refused(setup):
    assert await setup.subject_of(AccessTokenBuilder().build_hmac_with_the_public_key()) is None


async def test_it_does_not_even_look_for_keys_when_the_algorithm_is_wrong(setup):
    await setup.subject_of(AccessTokenBuilder().build_unsigned())

    assert setup.realm.reads == 0


async def test_a_token_from_another_issuer_is_refused(setup):
    token = AccessTokenBuilder().issued_by("http://evil.test/realms/agilina").build()

    assert await setup.subject_of(token) is None


@pytest.mark.parametrize("audience", ["account", ["account", "other-api"], None])
async def test_a_token_for_another_audience_is_refused(setup, audience):
    assert await setup.subject_of(AccessTokenBuilder().for_audience(audience).build()) is None


@pytest.mark.parametrize("token_type", ["ID", "Refresh", None])
async def test_only_access_tokens_are_accepted(setup, token_type):
    assert await setup.subject_of(AccessTokenBuilder().of_type(token_type).build()) is None


@pytest.mark.parametrize("subject", [None, "", "   ", 42])
async def test_a_token_needs_a_subject(setup, subject):
    assert await setup.subject_of(AccessTokenBuilder().for_subject(subject).build()) is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x.y.z", "....", "é.é.é"])
async def test_something_that_is_not_a_token_is_refused(setup, garbage):
    assert await setup.subject_of(garbage) is None


async def test_a_token_whose_header_has_no_key_id_is_refused(setup):
    import jwt

    token = jwt.encode(AccessTokenBuilder().claims(), KEY.private_key, algorithm="RS256")

    assert await setup.subject_of(token) is None


# ----------------------------------------------------------------- the realm's keys --
async def test_a_key_the_realm_added_is_found_by_reading_the_keys_again(setup):
    await setup.subject_of(AccessTokenBuilder().build())
    new_key = signing_key("key-2")
    setup.realm.rotate_to(KEY, new_key)
    setup.clock.advance(seconds=31)

    assert await setup.subject_of(AccessTokenBuilder().signed_with(new_key).build()) == SUBJECT
    assert setup.realm.reads == 2


async def test_a_flood_of_unknown_keys_does_not_flood_keycloak(setup):
    unknown = AccessTokenBuilder().signed_with(signing_key("nobody-knows-me")).build()

    for _ in range(5):
        assert await setup.subject_of(unknown) is None

    assert setup.realm.reads == 1


async def test_a_key_that_is_still_unknown_after_reading_the_keys_is_refused(setup):
    await setup.subject_of(AccessTokenBuilder().build())
    setup.clock.advance(seconds=31)

    unknown = AccessTokenBuilder().signed_with(signing_key("nobody-knows-me")).build()

    assert await setup.subject_of(unknown) is None
    assert setup.realm.reads == 2


async def test_the_encryption_key_of_the_realm_is_not_a_signing_key(setup):
    await setup.subject_of(AccessTokenBuilder().build())

    forged_as_encryption_key = AccessTokenBuilder().signed_with(signing_key("enc-1")).build()
    assert await setup.subject_of(forged_as_encryption_key) is None


@pytest.mark.parametrize(
    "answer",
    [
        {"status": 500, "body": {}},
        {"status": 200, "body": {"unexpected": []}},
        {"status": 200, "body": {"keys": ["not-a-key", {"kty": "RSA", "kid": "broken"}]}},
        {"status": 200, "body": "not json at all"},
    ],
)
async def test_when_the_realm_cannot_give_its_keys_nothing_is_trusted(setup, answer):
    setup.realm.status = answer["status"]
    setup.realm.body = answer["body"]

    assert await setup.subject_of(AccessTokenBuilder().build()) is None


async def test_a_published_key_without_a_name_cannot_be_used(setup):
    nameless = {name: value for name, value in KEY.jwk().items() if name != "kid"}
    setup.realm.body = {"keys": [nameless]}

    assert await setup.subject_of(AccessTokenBuilder().build()) is None


async def test_when_keycloak_is_unreachable_nothing_is_trusted_and_it_is_logged(setup, caplog):
    setup.realm.unreachable = True

    with caplog.at_level(logging.ERROR):
        assert await setup.subject_of(AccessTokenBuilder().build()) is None

    assert "could not be read" in caplog.text


async def test_the_keys_it_already_has_survive_a_failed_read(setup):
    await setup.subject_of(AccessTokenBuilder().build())
    setup.realm.unreachable = True
    setup.clock.advance(seconds=31)
    unknown = AccessTokenBuilder().signed_with(signing_key("later")).build()
    assert await setup.subject_of(unknown) is None

    assert await setup.subject_of(AccessTokenBuilder().build()) == SUBJECT


# ----------------------------------------------------------------------- the logs --
async def test_the_token_never_reaches_the_logs_but_the_reason_does(setup, caplog):
    token = AccessTokenBuilder().issued_by("http://evil.test/realms/agilina").build()

    with caplog.at_level(logging.INFO):
        await setup.subject_of(token)

    assert "issuer" in caplog.text
    assert token not in caplog.text
    assert token.split(".")[1] not in caplog.text


async def test_closing_it_closes_the_http_client(setup):
    await setup.verifier.aclose()

    assert setup.verifier._client.is_closed is True  # noqa: SLF001
