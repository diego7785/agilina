"""Add a tenant to the platform, or give every tenant of the catalog its realm (AD-29).

    make tenant-add slug=acme name="ACME Corporation" lang=en
    make tenant-realms                       # after Keycloak lost its data (make keycloak-reset)

Adding a tenant is four things, and this does all of them, in an order that can be repeated
after a failure halfway: the tenant's database is created and migrated, its realm is created in
Keycloak and its row is written in the catalog. Whoever runs it needs the tenant's two client
secrets in the environment (``AGILINA_TENANT_<SLUG>_KEYCLOAK_API_SECRET`` and
``AGILINA_TENANT_<SLUG>_KEYCLOAK_WORKER_SECRET``; ``make tenant-add`` generates them).
There is no panel for this: the administrators are the developers.
"""

import argparse
import sys

from sqlalchemy import create_engine, text

from agilina_api.bootstrap.migrate import migrate_platform, migrate_tenant
from agilina_api.identity.infrastructure.keycloak.realm_provisioner import (
    KeycloakRealmProvisioner,
    render_realm,
)
from agilina_api.shared.application.tenancy import is_valid_slug
from agilina_api.shared.infrastructure.settings import Settings, get_settings
from agilina_shared.enums import Language


def _provisioner(settings: Settings) -> KeycloakRealmProvisioner:
    return KeycloakRealmProvisioner(
        base_url=settings.keycloak_url,
        admin_user=settings.keycloak_admin_user,
        admin_password=settings.keycloak_admin_password.get_secret_value(),
    )


def _ensure_realm(
    settings: Settings, provisioner: KeycloakRealmProvisioner, slug: str, name: str, language: str
) -> None:
    api_secret = settings.tenant_api_secret(slug).get_secret_value()
    worker_secret = settings.tenant_worker_secret(slug).get_secret_value()
    for client, secret in (("API", api_secret), ("WORKER", worker_secret)):
        if not secret:
            raise SystemExit(
                f"AGILINA_TENANT_{slug.upper()}_KEYCLOAK_{client}_SECRET is not set: "
                "use make tenant-add"
            )
    realm = render_realm(settings.tenant_realm(slug), name, language, api_secret, worker_secret)
    created = provisioner.ensure_realm(realm)
    print(f"Realm {settings.tenant_realm(slug)}: {'created' if created else 'already there'}")


def add_tenant(settings: Settings, slug: str, name: str, language: Language) -> None:
    migrate_platform(settings)
    migrate_tenant(settings, slug)
    provisioner = _provisioner(settings)
    try:
        _ensure_realm(settings, provisioner, slug, name, language.value)
    finally:
        provisioner.close()
    engine = create_engine(settings.platform_dsn)
    try:
        with engine.begin() as connection:
            inserted = connection.execute(
                text(
                    "INSERT INTO tenant (slug, display_name, language) "
                    "VALUES (:slug, :name, :language) ON CONFLICT (slug) DO NOTHING"
                ),
                {"slug": slug, "name": name, "language": language.value},
            ).rowcount
    finally:
        engine.dispose()
    print(f"Tenant {slug}: {'added to the catalog' if inserted else 'already in the catalog'}")


def create_missing_realms(settings: Settings) -> None:
    engine = create_engine(settings.platform_dsn)
    try:
        with engine.connect() as connection:
            tenants = connection.execute(
                text("SELECT slug, display_name, language FROM tenant ORDER BY slug")
            ).all()
    finally:
        engine.dispose()
    provisioner = _provisioner(settings)
    try:
        for tenant in tenants:
            _ensure_realm(settings, provisioner, tenant.slug, tenant.display_name, tenant.language)
    finally:
        provisioner.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Add a tenant to the platform.")
    parser.add_argument("--slug", help="short name: lowercase letters and digits, e.g. acme")
    parser.add_argument("--name", help="display name of the organization")
    parser.add_argument("--lang", choices=[language.value for language in Language], default="es")
    parser.add_argument(
        "--realms-only", action="store_true", help="create the missing realms of the catalog"
    )
    arguments = parser.parse_args()
    settings = get_settings()
    if arguments.realms_only:
        create_missing_realms(settings)
        return 0
    if not arguments.slug or not arguments.name:
        parser.error("--slug and --name are required")
    if not is_valid_slug(arguments.slug):
        print(
            f"'{arguments.slug}' is not a valid slug: lowercase letters and digits, starting "
            "with a letter, 2 to 31 characters, and not platform, admin or api",
            file=sys.stderr,
        )
        return 1
    add_tenant(settings, arguments.slug, arguments.name.strip(), Language(arguments.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
