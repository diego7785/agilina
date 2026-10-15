"""Creating the realm of a tenant: the template with its values, and the calls to Keycloak."""

import json

import httpx
import pytest

from agilina_api.identity.infrastructure.keycloak.realm_provisioner import (
    TEMPLATE,
    KeycloakRealmProvisioner,
    render_realm,
)


def _realm(**overrides) -> dict:
    values = {
        "realm": "agilina-acme",
        "name": "ACME Corporation",
        "locale": "en",
        "api_secret": "the-secret",
        "worker_secret": "the-worker-secret",
    }
    values.update(overrides)
    return render_realm(**values)


def _clients(realm: dict) -> dict[str, dict]:
    return {client["clientId"]: client for client in realm["clients"]}


# ---------------------------------------------------------------------------- template --
def test_the_realm_gets_the_name_the_display_name_and_the_language_of_the_tenant():
    realm = _realm(realm="agilina-ecomoda", name="Ecomoda", locale="es")

    assert realm["realm"] == "agilina-ecomoda"
    assert realm["displayName"] == "Ecomoda"
    assert realm["defaultLocale"] == "es"
    assert realm["loginTheme"] == "agilina"  # every tenant has the same login


def test_the_api_client_of_the_realm_has_the_secret_of_its_tenant():
    clients = _clients(_realm(api_secret="acme-secret"))

    assert clients["agilina-api"]["secret"] == "acme-secret"


def test_the_worker_client_signs_in_with_the_secret_of_its_tenant_for_the_api():
    """Client credentials only, with the tenant's own secret, and its tokens carry the
    audience ``agilina-api`` so the API's verifier accepts them (AGI-64)."""
    worker = _clients(_realm(worker_secret="acme-worker-secret"))["agilina-worker"]

    assert worker["secret"] == "acme-worker-secret"
    assert worker["clientAuthenticatorType"] == "client-secret"
    assert worker["publicClient"] is False and worker["serviceAccountsEnabled"] is True
    assert worker["standardFlowEnabled"] is False
    assert worker["directAccessGrantsEnabled"] is False
    assert worker["implicitFlowEnabled"] is False
    assert [
        mapper["config"]["included.client.audience"]
        for mapper in worker["protocolMappers"]
        if mapper["protocolMapper"] == "oidc-audience-mapper"
    ] == ["agilina-api"]


def test_each_client_gets_its_own_secret():
    clients = _clients(_realm(api_secret="api-secret", worker_secret="worker-secret"))

    assert clients["agilina-api"]["secret"] == "api-secret"
    assert clients["agilina-worker"]["secret"] == "worker-secret"
    assert "secret" not in clients["agilina-web"]


def test_no_placeholder_is_left_behind():
    assert "${" not in json.dumps(_realm())


def test_a_name_with_quotes_cannot_break_out_of_its_string():
    realm = _realm(name='Acme "Corp" \\ Inc')

    assert realm["displayName"] == 'Acme "Corp" \\ Inc'
    assert _clients(realm)["agilina-api"]["secret"] == "the-secret"  # the rest is untouched


def test_every_realm_keeps_what_makes_the_login_safe():
    realm = _realm()
    web = _clients(realm)["agilina-web"]

    assert realm["registrationAllowed"] is False
    assert realm["bruteForceProtected"] is True
    assert realm["resetPasswordAllowed"] is False
    assert web["attributes"]["pkce.code.challenge.method"] == "S256"
    assert web["publicClient"] is True and web["directAccessGrantsEnabled"] is False
    assert any(
        mapper["protocolMapper"] == "oidc-audience-mapper"
        and mapper["config"]["included.client.audience"] == "agilina-api"
        for mapper in web["protocolMappers"]
    )


def test_what_keycloak_stores_in_a_short_column_fits_in_it():
    """A description over 255 characters makes Keycloak answer "Database operation failed"
    when the realm is created, and nothing says why."""
    for client in _realm()["clients"]:
        assert len(client.get("description", "")) <= 255, client["clientId"]


def test_the_template_is_a_file_of_the_repository():
    assert TEMPLATE.is_file() and TEMPLATE.name == "realm-template.json"


# ------------------------------------------------------------------------- keycloak --
class _Keycloak:
    """Answers like Keycloak and remembers what it was asked."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.existing: set[str] = set()
        self.token_status = 200
        self.lookup_status: int | None = None
        self.create_status = 201

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/protocol/openid-connect/token"):
            if self.token_status != 200:
                return httpx.Response(self.token_status)
            return httpx.Response(200, json={"access_token": "admin-token"})
        if request.method == "GET":
            name = request.url.path.rsplit("/", 1)[-1]
            if self.lookup_status is not None:
                return httpx.Response(self.lookup_status)
            return httpx.Response(200 if name in self.existing else 404)
        return httpx.Response(self.create_status)

    def provisioner(self) -> KeycloakRealmProvisioner:
        return KeycloakRealmProvisioner(
            base_url="http://kc/",
            admin_user="admin",
            admin_password="the-password",  # noqa: S106
            client=httpx.Client(transport=httpx.MockTransport(self.handler)),
        )

    def methods(self) -> list[str]:
        return [request.method for request in self.requests]


def test_a_realm_that_does_not_exist_is_created_as_the_administrator():
    keycloak = _Keycloak()

    created = keycloak.provisioner().ensure_realm(_realm())

    assert created is True
    token, lookup, creation = keycloak.requests
    assert dict(item.split("=") for item in token.content.decode().split("&")) == {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": "admin",
        "password": "the-password",
    }
    assert lookup.url.path == "/admin/realms/agilina-acme"
    assert creation.url.path == "/admin/realms"
    assert creation.headers["Authorization"] == "Bearer admin-token"
    assert json.loads(creation.content)["realm"] == "agilina-acme"


def test_a_realm_that_exists_is_left_alone():
    keycloak = _Keycloak()
    keycloak.existing.add("agilina-acme")

    assert keycloak.provisioner().ensure_realm(_realm()) is False
    assert "POST" not in keycloak.methods()[1:]  # only the token request is a POST


def test_wrong_administrator_credentials_are_reported_without_echoing_them():
    keycloak = _Keycloak()
    keycloak.token_status = 401

    with pytest.raises(RuntimeError, match="refused the administrator's credentials") as raised:
        keycloak.provisioner().ensure_realm(_realm())

    assert "the-password" not in str(raised.value)


def test_an_unexpected_answer_when_looking_for_the_realm_is_an_error():
    keycloak = _Keycloak()
    keycloak.lookup_status = 500

    with pytest.raises(RuntimeError, match="500 looking for realm agilina-acme"):
        keycloak.provisioner().ensure_realm(_realm())


def test_a_realm_that_cannot_be_created_is_an_error():
    keycloak = _Keycloak()
    keycloak.create_status = 400

    with pytest.raises(RuntimeError, match="400 creating realm agilina-acme"):
        keycloak.provisioner().ensure_realm(_realm())


def test_closing_it_closes_its_http_client():
    keycloak = _Keycloak()
    provisioner = keycloak.provisioner()

    provisioner.close()

    assert provisioner._client.is_closed is True  # noqa: SLF001
