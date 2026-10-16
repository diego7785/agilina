"""``make tenant-add``: a database, a realm and a row in the catalog, with Keycloak doubled."""

import sys
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect, text

from agilina_api.bootstrap import tenant_admin
from agilina_api.shared.infrastructure.migrations import drop_database
from agilina_shared.enums import Language
from tests.api.integration.conftest import PlatformDatabases

pytestmark = pytest.mark.integration


class FakeProvisioner:
    """Keycloak, as the operator's tool sees it: which realms it was asked to create."""

    def __init__(self) -> None:
        self.realms: list[dict] = []
        self.known: set[str] = set()
        self.closed = False

    def ensure_realm(self, realm: dict) -> bool:
        self.realms.append(realm)
        created = realm["realm"] not in self.known
        self.known.add(realm["realm"])
        return created

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def keycloak(monkeypatch) -> FakeProvisioner:
    provisioner = FakeProvisioner()
    monkeypatch.setattr(tenant_admin, "_provisioner", lambda settings: provisioner)
    monkeypatch.setenv("AGILINA_TENANT_WONKA_KEYCLOAK_API_SECRET", "wonka-secret")
    monkeypatch.setenv("AGILINA_TENANT_WONKA_KEYCLOAK_WORKER_SECRET", "wonka-worker-secret")
    return provisioner


@pytest.fixture
def wonka(platform_databases: PlatformDatabases) -> Iterator[PlatformDatabases]:
    """Wonka is added by the test: whatever it leaves behind is removed afterwards."""
    yield platform_databases
    settings = platform_databases.settings
    catalog = create_engine(settings.platform_dsn)
    with catalog.begin() as connection:
        connection.execute(text("DELETE FROM tenant WHERE slug = 'wonka'"))
    catalog.dispose()
    drop_database(settings.admin_dsn, f"{platform_databases.prefix}wonka")


def _row(settings, slug="wonka"):
    catalog = create_engine(settings.platform_dsn)
    try:
        with catalog.connect() as connection:
            return connection.execute(
                text("SELECT display_name, language, status FROM tenant WHERE slug = :s"),
                {"s": slug},
            ).one_or_none()
    finally:
        catalog.dispose()


def test_adding_a_tenant_creates_its_database_its_realm_and_its_row(wonka, keycloak, capsys):
    settings = wonka.settings

    tenant_admin.add_tenant(settings, "wonka", "Wonka Industries", Language.EN)

    engine = create_engine(settings.tenant_dsn("wonka"))
    with engine.connect() as connection:
        assert "team_member" in inspect(connection).get_table_names()
    engine.dispose()
    [realm] = keycloak.realms
    assert realm["realm"] == "agilina-wonka" and realm["defaultLocale"] == "en"
    assert tuple(_row(settings)) == ("Wonka Industries", "en", "active")
    assert keycloak.closed is True
    out = capsys.readouterr().out
    assert "created" in out and "added to the catalog" in out


def test_adding_it_again_changes_nothing(wonka, keycloak, capsys):
    settings = wonka.settings
    tenant_admin.add_tenant(settings, "wonka", "Wonka Industries", Language.EN)
    capsys.readouterr()

    tenant_admin.add_tenant(settings, "wonka", "Another Name", Language.ES)

    out = capsys.readouterr().out
    assert "already there" in out and "already in the catalog" in out
    assert tuple(_row(settings)) == ("Wonka Industries", "en", "active")  # the first one stays


def test_a_failure_halfway_can_be_repeated(wonka, keycloak, monkeypatch):
    """Keycloak is down the first time: the database exists but the tenant is not in the
    catalog yet, so nobody can reach a half-made tenant; running it again finishes it."""
    settings = wonka.settings

    def down(realm):
        raise RuntimeError("Keycloak answered 503")

    original = keycloak.ensure_realm
    monkeypatch.setattr(keycloak, "ensure_realm", down)
    with pytest.raises(RuntimeError):
        tenant_admin.add_tenant(settings, "wonka", "Wonka Industries", Language.EN)
    assert _row(settings) is None

    monkeypatch.setattr(keycloak, "ensure_realm", original)
    tenant_admin.add_tenant(settings, "wonka", "Wonka Industries", Language.EN)

    assert _row(settings) is not None


def test_a_tenant_without_its_secret_is_not_added(wonka, keycloak, monkeypatch):
    monkeypatch.delenv("AGILINA_TENANT_WONKA_KEYCLOAK_API_SECRET")

    with pytest.raises(SystemExit, match="AGILINA_TENANT_WONKA_KEYCLOAK_API_SECRET"):
        tenant_admin.add_tenant(wonka.settings, "wonka", "Wonka Industries", Language.EN)

    assert _row(wonka.settings) is None


def test_a_tenant_without_the_secret_of_its_worker_is_not_added(wonka, keycloak, monkeypatch):
    monkeypatch.delenv("AGILINA_TENANT_WONKA_KEYCLOAK_WORKER_SECRET")

    with pytest.raises(SystemExit, match="AGILINA_TENANT_WONKA_KEYCLOAK_WORKER_SECRET"):
        tenant_admin.add_tenant(wonka.settings, "wonka", "Wonka Industries", Language.EN)

    assert keycloak.realms == []
    assert _row(wonka.settings) is None


def test_the_realm_of_a_tenant_gets_the_secrets_of_its_two_clients(wonka, keycloak):
    tenant_admin.add_tenant(wonka.settings, "wonka", "Wonka Industries", Language.EN)

    [realm] = keycloak.realms
    secrets = {client["clientId"]: client.get("secret") for client in realm["clients"]}
    assert secrets["agilina-api"] == "wonka-secret"
    assert secrets["agilina-worker"] == "wonka-worker-secret"


def test_every_tenant_of_the_catalog_gets_its_realm(platform_databases, keycloak, monkeypatch):
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_API_SECRET", "acme-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_API_SECRET", "ecomoda-secret")
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_WORKER_SECRET", "acme-worker-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_WORKER_SECRET", "ecomoda-worker-secret")

    tenant_admin.create_missing_realms(platform_databases.settings)

    assert {realm["realm"]: realm["defaultLocale"] for realm in keycloak.realms} == {
        "agilina-acme": "en",
        "agilina-ecomoda": "es",
    }
    assert keycloak.closed is True


def test_the_command_line_adds_a_tenant(wonka, keycloak, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["tenant-add", "--slug", "wonka", "--name", "  Wonka Industries ", "--lang", "es"],
    )

    assert tenant_admin.main() == 0
    assert tuple(_row(wonka.settings)) == ("Wonka Industries", "es", "active")


def test_the_command_line_can_only_create_the_realms(platform_databases, keycloak, monkeypatch):
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_API_SECRET", "acme-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_API_SECRET", "ecomoda-secret")
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_WORKER_SECRET", "acme-worker-secret")
    monkeypatch.setenv("AGILINA_TENANT_ECOMODA_KEYCLOAK_WORKER_SECRET", "ecomoda-worker-secret")
    monkeypatch.setattr(sys, "argv", ["tenant-add", "--realms-only"])

    assert tenant_admin.main() == 0
    assert len(keycloak.realms) == 2
