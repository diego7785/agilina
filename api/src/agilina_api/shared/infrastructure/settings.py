"""API settings.

Everything is read from environment variables: the repository stores no real
value, only the example file with the expected keys (Avance 1, 7.1).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agilina_api.shared.infrastructure.mail.smtp_mailer import SmtpSecurity
from agilina_shared.enums import Language

REPO_ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    """Environment values of the API.

    Keys prefixed with ``AGILINA_`` belong to the product; the Postgres ones
    keep their standard name because the containers share them.
    """

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        env_prefix="AGILINA_",
        extra="ignore",
    )

    # --------------------------------------------------------- environment --
    environment: Literal["local", "cloud"] = "local"
    log_level: str = "INFO"
    default_language: Language = Language.ES

    # ----------------------------------------------------------------- api --
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_public_url: str = "http://localhost:8000"
    web_public_url: str = "http://localhost:4200"
    """Where the web application is served: the activation link in an invitation points here."""
    allowed_origins: str = "http://localhost:4200"

    # ------------------------------------------------------------ postgres --
    # One PostgreSQL server, several databases (AD-29): the platform's catalog of tenants
    # and one database per tenant. ``POSTGRES_DB`` is only the database the server always
    # has, the one that is connected to in order to create the others.
    postgres_user: str = Field(default="agilina", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="agilina", validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="agilina", validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    platform_db: str = "agilina_platform"
    """The catalog: which tenants exist, and the scheduler's jobs."""
    tenant_db_prefix: str = "agilina_"
    """The database of a tenant is this prefix and its slug (``agilina_acme``)."""

    # ------------------------------------------------------------ keycloak --
    keycloak_url: str = "http://localhost:8080"
    tenant_realm_prefix: str = "agilina-"
    """The realm of a tenant is this prefix and its slug (``agilina-acme``)."""
    keycloak_public_url: str = "http://localhost:8080"
    """The URL the browser reaches Keycloak at: the issuer of every token it signs. It can
    differ from ``keycloak_url``, which is the one the API itself uses (inside Compose,
    ``http://keycloak:8080``)."""
    keycloak_admin_user: str = Field(default="admin", validation_alias="KEYCLOAK_ADMIN")
    keycloak_admin_password: SecretStr = Field(
        default=SecretStr(""), validation_alias="KEYCLOAK_ADMIN_PASSWORD"
    )
    """Keycloak's own administrator: only the operator's tools use it, to create realms."""
    keycloak_web_client: str = "agilina-web"
    keycloak_worker_client: str = "agilina-worker"
    keycloak_api_client: str = "agilina-api"

    # ---------------------------------------------------------------- email --
    # Which server delivers the email is only configuration (AD-23). The defaults point
    # to Mailpit, the development and CI inbox; see .env.example for Amazon SES.
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: SmtpSecurity = "none"
    mail_from: str = "Agilina <no-reply@agilina.local>"

    # ------------------------------------------------------------- livekit --
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: SecretStr = SecretStr("")

    # ------------------------------------------------------ model services --
    stt_url: str = "http://localhost:8001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    elevenlabs_api_key: str = ""

    def server_dsn(self, database: str) -> str:
        """Connection URL of ``database`` on the PostgreSQL server.

        ``psycopg`` serves both uses of the project with the same string:
        asynchronous for the API and synchronous for Alembic and the scheduler
        store.
        """
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{database}"
        )

    @property
    def platform_dsn(self) -> str:
        return self.server_dsn(self.platform_db)

    @property
    def admin_dsn(self) -> str:
        """The database the server always has: where the others are created from."""
        return self.server_dsn(self.postgres_db)

    def tenant_dsn(self, slug: str) -> str:
        return self.server_dsn(f"{self.tenant_db_prefix}{slug}")

    def tenant_realm(self, slug: str) -> str:
        return f"{self.tenant_realm_prefix}{slug}"

    def tenant_api_secret(self, slug: str) -> SecretStr:
        """The secret of the ``agilina-api`` client of the tenant's realm: one per tenant,
        in ``AGILINA_TENANT_<SLUG>_KEYCLOAK_API_SECRET``. Never in the repository."""
        return SecretStr(os.environ.get(f"AGILINA_TENANT_{slug.upper()}_KEYCLOAK_API_SECRET", ""))

    def tenant_worker_secret(self, slug: str) -> SecretStr:
        """The secret of the ``agilina-worker`` client of the tenant's realm, in
        ``AGILINA_TENANT_<SLUG>_KEYCLOAK_WORKER_SECRET``. The API only writes it into the realm
        it creates; the worker uses it to sign in. Never in the repository."""
        return SecretStr(
            os.environ.get(f"AGILINA_TENANT_{slug.upper()}_KEYCLOAK_WORKER_SECRET", "")
        )

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings: read once per process."""
    return Settings()
