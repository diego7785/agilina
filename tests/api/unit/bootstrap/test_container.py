"""The composition root builds the whole object graph of a tenant without connecting to anything."""

from agilina_api.bootstrap.container import build_container
from agilina_api.identity.infrastructure.keycloak.authenticated_users import (
    KeycloakAuthenticatedUsers,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from agilina_api.shared.infrastructure.settings import get_settings
from tests.api.builders import TenantBuilder


def _container(tenant_slug: str = "acme"):
    return build_container(get_settings(), TenantBuilder().with_slug(tenant_slug).build())


def test_the_graph_is_built_without_postgres_keycloak_or_a_mail_server():
    container = _container()

    assert container.activate_account is not None
    assert container.issue_invitation is not None
    assert container.request_new_invitation is not None
    assert container.invitation_status is not None
    assert container.create_team is not None
    assert container.create_team_as_admin is not None
    assert container.list_my_teams is not None
    assert container.get_team is not None
    assert container.invite_to_team is not None
    assert container.list_team_members is not None
    assert container.change_member_role is not None
    assert container.remove_member is not None
    assert container.start_sprint is not None
    assert container.reconfigure_sprint is not None
    assert container.get_active_sprint is not None
    assert container.get_ceremony_context is not None
    assert container.deliver_ceremony_result is not None


def test_the_links_of_the_emails_open_the_web_of_the_tenant_from_its_public_url(monkeypatch):
    """The activation link goes to ``/<tenant>/activate`` and the notice to an existing account
    to ``/<tenant>/teams/<id>``, both under ``AGILINA_WEB_PUBLIC_URL`` (HU-02, HU-06, AD-29)."""
    monkeypatch.setenv("AGILINA_WEB_PUBLIC_URL", "https://agilina.example/")
    get_settings.cache_clear()

    container = _container("ecomoda")

    assert container.issue_invitation._activation_url == (  # noqa: SLF001
        "https://agilina.example/ecomoda/activate"
    )
    assert container.invite_to_team._teams_url == "https://agilina.example/ecomoda/teams"  # noqa: SLF001


def test_the_tokens_are_validated_against_the_realm_of_the_tenant_by_its_public_url(monkeypatch):
    monkeypatch.setenv("AGILINA_KEYCLOAK_URL", "http://keycloak:8080")
    monkeypatch.setenv("AGILINA_KEYCLOAK_PUBLIC_URL", "http://localhost:8080/")
    get_settings.cache_clear()

    container = _container("ecomoda")

    assert isinstance(container.authenticated_users, KeycloakAuthenticatedUsers)
    verifier = container.access_token_verifier
    # The issuer a token carries is the public one; the keys are read through the internal one.
    assert verifier._issuer == "http://localhost:8080/realms/agilina-ecomoda"  # noqa: SLF001
    assert verifier._audience == "agilina-api"  # noqa: SLF001
    assert verifier._jwks_url == (  # noqa: SLF001
        "http://keycloak:8080/realms/agilina-ecomoda/protocol/openid-connect/certs"
    )


def test_the_worker_is_recognized_by_its_client_with_the_verifier_of_the_tenant():
    """The same verifier as a person's, so a worker token of another realm is not valid."""
    container = _container("ecomoda")

    workers = container.authenticated_workers
    assert isinstance(workers, KeycloakAuthenticatedWorkers)
    assert workers._verifier is container.access_token_verifier  # noqa: SLF001
    assert workers._worker_client == "agilina-worker"  # noqa: SLF001


def test_the_api_client_uses_the_secret_of_its_tenant(monkeypatch):
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_API_SECRET", "acme-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_API_SECRET", "ecomoda-secret")

    assert _container("acme").identity_provider._client_secret == "acme-secret"  # noqa: SLF001
    assert _container("ecomoda").identity_provider._client_secret == "ecomoda-secret"  # noqa: SLF001


def test_the_invitation_link_names_the_tenant():
    # The link of the email: the web needs the tenant to know which login to open.
    container = _container("ecomoda")

    assert container.issue_invitation._activation_url.endswith("/ecomoda/activate")  # noqa: SLF001


def test_the_membership_is_checked_against_the_stored_teams():
    container = _container()

    assert container.team_access is container.team_queries


async def test_closing_the_container_closes_what_it_opened():
    container = _container()

    await container.aclose()

    assert container.identity_provider._client.is_closed is True  # noqa: SLF001
    assert container.access_token_verifier._client.is_closed is True  # noqa: SLF001
