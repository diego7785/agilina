"""Integration tests run against a real PostgreSQL (``make test-integration``).

Each run creates throwaway databases shaped like the platform's (AD-29): a catalog and two
tenants, ``acme`` (in English) and ``ecomoda`` (in Spanish), each with every migration applied.
The names carry a random prefix, so the schema under test is the one the migrations really
produce and the developer's own data is never touched. The fixtures ``engine`` and
``session_factory`` are the database of ``acme``; ``ecomoda_engine`` and
``ecomoda_session_factory`` are the other tenant's, to show that the two never mix.
"""

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from agilina_api.shared.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agilina_api.shared.infrastructure.migrations import drop_database, ensure_database, migrate
from agilina_api.shared.infrastructure.settings import Settings, get_settings

TABLES = (
    "ceremony_event, transcript_segment, ceremony_result, ceremony, sprint_participant, sprint, "
    "invitation, team_member, team, app_user"
)

TENANTS = (("acme", "ACME Corporation", "en"), ("ecomoda", "Ecomoda", "es"))


@dataclass(frozen=True)
class PlatformDatabases:
    """The databases of this run: where they are and how they are named."""

    settings: Settings
    prefix: str

    def tenant_dsn(self, slug: str) -> str:
        return self.settings.tenant_dsn(slug)


@pytest.fixture(scope="session")
def platform_databases() -> Iterator[PlatformDatabases]:
    """The catalog and the databases of ``acme`` and ``ecomoda``, migrated; dropped at the end."""
    prefix = f"it{uuid.uuid4().hex[:10]}_"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("AGILINA_PLATFORM_DB", f"{prefix}platform")
        patch.setenv("AGILINA_TENANT_DB_PREFIX", prefix)
        get_settings.cache_clear()
        settings = get_settings()

        ensure_database(settings.admin_dsn, settings.platform_db)
        migrate("platform", settings.platform_dsn)
        catalog = create_engine(settings.platform_dsn)
        with catalog.begin() as connection:
            for slug, name, language in TENANTS:
                connection.execute(
                    text("INSERT INTO tenant (slug, display_name, language) VALUES (:s, :n, :l)"),
                    {"s": slug, "n": name, "l": language},
                )
        catalog.dispose()
        for slug, _, _ in TENANTS:
            ensure_database(settings.admin_dsn, f"{prefix}{slug}")
            migrate("tenant", settings.tenant_dsn(slug))

        yield PlatformDatabases(settings, prefix)

        for slug, _, _ in TENANTS:
            drop_database(settings.admin_dsn, f"{prefix}{slug}")
        drop_database(settings.admin_dsn, settings.platform_db)
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def admin_dsn(platform_databases: PlatformDatabases) -> str:
    return platform_databases.settings.admin_dsn


@pytest.fixture(scope="session")
def database_url(platform_databases: PlatformDatabases) -> str:
    """The database of ``acme``, the tenant of the tests that name none."""
    return platform_databases.tenant_dsn("acme")


async def _clean_engine(dsn: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(dsn, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    async for engine in _clean_engine(database_url):
        yield engine


@pytest.fixture
async def ecomoda_engine(platform_databases: PlatformDatabases) -> AsyncIterator[AsyncEngine]:
    async for engine in _clean_engine(platform_databases.tenant_dsn("ecomoda")):
        yield engine


@pytest.fixture
async def platform_engine(platform_databases: PlatformDatabases) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(platform_databases.settings.platform_dsn, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def ecomoda_session_factory(ecomoda_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(ecomoda_engine, expire_on_commit=False)


@pytest.fixture
def uow(session_factory: async_sessionmaker[AsyncSession]) -> SqlAlchemyUnitOfWork:
    """A new unit of work; use it with ``async with``."""
    return SqlAlchemyUnitOfWork(session_factory)
