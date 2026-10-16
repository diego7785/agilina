"""Creating the realm of a tenant in the real Keycloak, from the template (AD-29).

Run with ``make test-keycloak``. A realm made from the template must work: its ``agilina-api``
client has the secret it was given and the right to manage users, which is all the API needs to
activate an account. The realm is removed afterwards.
"""

import secrets
import uuid
from collections.abc import Iterator

import httpx
import pytest

from agilina_api.identity.domain.value_objects import Email
from agilina_api.identity.infrastructure.keycloak.identity_provider import KeycloakIdentityProvider
from agilina_api.identity.infrastructure.keycloak.realm_provisioner import (
    KeycloakRealmProvisioner,
    render_realm,
)

pytestmark = pytest.mark.keycloak


@pytest.fixture
def provisioner(settings) -> Iterator[KeycloakRealmProvisioner]:
    provisioner = KeycloakRealmProvisioner(
        base_url=settings.keycloak_url,
        admin_user=settings.keycloak_admin_user,
        admin_password=settings.keycloak_admin_password.get_secret_value(),
    )
    yield provisioner
    provisioner.close()


def _delete_realm(settings, name: str) -> None:
    token = httpx.post(
        f"{settings.keycloak_url}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": settings.keycloak_admin_user,
            "password": settings.keycloak_admin_password.get_secret_value(),
        },
    ).json()["access_token"]
    httpx.delete(
        f"{settings.keycloak_url}/admin/realms/{name}",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_a_realm_made_from_the_template_works_and_is_made_only_once(settings, provisioner):
    name = f"agilina-it{uuid.uuid4().hex[:8]}"
    api_secret = secrets.token_hex(16)
    realm = render_realm(name, "Throwaway", "es", api_secret, secrets.token_hex(16))
    try:
        assert provisioner.ensure_realm(realm) is True
        assert provisioner.ensure_realm(realm) is False

        api = KeycloakIdentityProvider(
            base_url=settings.keycloak_url,
            realm=name,
            client_id=settings.keycloak_api_client,
            client_secret=api_secret,
        )
        subject = await api.create_user(
            email=Email(f"it-{uuid.uuid4().hex[:8]}@example.test"),
            full_name="Julián Torres",
            password="a-very-long-password-1",  # noqa: S106
        )
        assert subject
        await api.aclose()
    finally:
        _delete_realm(settings, name)


def test_the_administrator_credentials_are_checked(settings):
    wrong = KeycloakRealmProvisioner(
        base_url=settings.keycloak_url,
        admin_user="admin",
        admin_password="not-the-password",  # noqa: S106
    )

    with pytest.raises(RuntimeError, match="refused the administrator's credentials"):
        wrong.ensure_realm({"realm": "agilina-nobody"})
    wrong.close()
