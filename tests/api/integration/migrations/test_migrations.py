"""The migrations produce the schema the reference DDL defines (with AD-22, the sprint of
HU-06 and the daily's time and participants of HU-07), and the ORM models agree with it."""

import uuid
from datetime import date

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from agilina_api.ceremonies.infrastructure.persistence import orm_models as ceremonies_models
from agilina_api.identity.infrastructure.persistence import orm_models as identity_models
from agilina_api.shared.infrastructure.database.base import Base
from agilina_api.shared.infrastructure.migrations import (
    alembic_config,
    drop_database,
    ensure_database,
)
from agilina_api.teams.infrastructure.persistence import orm_models as teams_models

pytestmark = pytest.mark.integration

_REGISTERED = (
    ceremonies_models,
    identity_models,
    teams_models,
)  # the models must be imported to be in the metadata


async def _columns(engine: AsyncEngine, table: str) -> dict[str, bool]:
    """Column name → nullable, as the database reports it."""
    async with engine.connect() as connection:
        found = await connection.run_sync(lambda sync: inspect(sync).get_columns(table))
    return {column["name"]: column["nullable"] for column in found}


async def test_every_table_the_story_needs_exists(engine: AsyncEngine):
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

    assert {
        "app_user",
        "team",
        "team_member",
        "invitation",
        "sprint",
        "sprint_participant",
        "ceremony",
        "alembic_version",
    } <= tables


async def test_citext_and_the_enums_exist(engine: AsyncEngine):
    async with engine.connect() as connection:
        extensions = {
            row[0] for row in await connection.execute(text("SELECT extname FROM pg_extension"))
        }
        enums = {
            row[0]
            for row in await connection.execute(
                text("SELECT typname FROM pg_type WHERE typtype = 'e'")
            )
        }

    assert "citext" in extensions
    assert {
        "team_mode",
        "team_language",
        "team_role",
        "membership_status",
        "invitation_status",
        "sprint_status",
    } <= enums


@pytest.mark.parametrize("table", ["team", "invitation"])
async def test_created_by_accepts_null_for_the_platform_operator_ad_22(
    engine: AsyncEngine, table: str
):
    assert (await _columns(engine, table))["created_by"] is True


@pytest.mark.parametrize(
    "table",
    ["app_user", "team", "team_member", "invitation", "sprint", "sprint_participant", "ceremony"],
)
async def test_every_orm_column_exists_in_the_database_with_the_same_nullability(
    engine: AsyncEngine, table: str
):
    in_database = await _columns(engine, table)

    for column in Base.metadata.tables[table].columns:
        assert column.name in in_database, f"{table}.{column.name} is not in the database"
        assert column.nullable == in_database[column.name], f"{table}.{column.name} nullability"


async def test_the_partial_unique_index_on_pending_invitations_exists(engine: AsyncEngine):
    async with engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname = 'invitation_pending_unique'"
                )
            )
        ).scalar_one()

    assert "UNIQUE" in definition and "status = 'pending'" in definition


async def test_the_database_rejects_a_team_name_longer_than_80(engine: AsyncEngine):
    """The ``team_name_max_length`` check backs the domain rule: 80 is fine, 81 is not."""
    insert = text("INSERT INTO team (name) VALUES (:name)")
    async with engine.begin() as connection:
        await connection.execute(insert, {"name": "x" * 80})
        await connection.execute(insert, {"name": "🚀" * 80})  # characters, not bytes

    with pytest.raises(IntegrityError, match="team_name_max_length"):
        async with engine.begin() as connection:
            await connection.execute(insert, {"name": "x" * 81})


async def test_the_sprint_statuses_are_the_glossarys(engine: AsyncEngine):
    async with engine.connect() as connection:
        labels = (
            await connection.execute(text("SELECT unnest(enum_range(NULL::sprint_status))::text"))
        ).scalars()

    assert list(labels) == ["planned", "active", "closed"]


async def _a_team(engine: AsyncEngine) -> str:
    async with engine.begin() as connection:
        return str(
            (
                await connection.execute(
                    text("INSERT INTO team (name) VALUES ('Atlas') RETURNING id")
                )
            ).scalar_one()
        )


# The daily's time is required (HU-07); its value does not matter to these tests. The number is
# required too (HU-12): a test that stores several sprints of a team gives each its own.
_SPRINT = text(
    "INSERT INTO sprint (team_id, number, start_date, end_date, status, daily_time_utc, "
    "daily_time_zone) "
    "VALUES (:team, :number, :start, :end, CAST(:status AS sprint_status), "
    "'2026-10-05T14:00:00Z', 'America/Bogota')"
)


async def test_a_new_sprint_is_planned_and_cannot_end_before_it_starts(engine: AsyncEngine):
    team = await _a_team(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO sprint (team_id, number, start_date, end_date, daily_time_utc, "
                "daily_time_zone) VALUES (:t, 1, :d, :d, '2026-10-05T14:00:00Z', 'America/Bogota')"
            ),
            {"t": team, "d": date(2026, 10, 5)},
        )
        status = (await connection.execute(text("SELECT status::text FROM sprint"))).scalar_one()
    assert status == "planned"

    with pytest.raises(IntegrityError, match="sprint_dates_ordered"):
        async with engine.begin() as connection:
            await connection.execute(
                _SPRINT,
                {
                    "team": team,
                    "number": 2,
                    "start": date(2026, 10, 5),
                    "end": date(2026, 10, 4),
                    "status": "planned",
                },
            )


async def test_a_team_has_at_most_one_active_sprint_but_any_number_of_closed_ones(
    engine: AsyncEngine,
):
    team = await _a_team(engine)
    dates = {"start": date(2026, 10, 5), "end": date(2026, 10, 16)}
    async with engine.begin() as connection:
        for number, status in enumerate(("closed", "closed", "active"), start=1):
            await connection.execute(
                _SPRINT, {"team": team, "number": number, "status": status, **dates}
            )

    with pytest.raises(IntegrityError, match="sprint_one_active_per_team"):
        async with engine.begin() as connection:
            await connection.execute(
                _SPRINT, {"team": team, "number": 4, "status": "active", **dates}
            )


async def test_deleting_a_team_deletes_its_sprints(engine: AsyncEngine):
    team = await _a_team(engine)
    async with engine.begin() as connection:
        await connection.execute(
            _SPRINT,
            {
                "team": team,
                "number": 1,
                "start": date(2026, 10, 5),
                "end": date(2026, 10, 16),
                "status": "active",
            },
        )
        await connection.execute(text("DELETE FROM team WHERE id = :id"), {"id": team})
        remaining = (await connection.execute(text("SELECT count(*) FROM sprint"))).scalar_one()

    assert remaining == 0


async def test_a_sprint_keeps_its_updated_at_current(engine: AsyncEngine):
    """The ``set_updated_at`` trigger of every table also runs on ``sprint``."""
    team = await _a_team(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO sprint (team_id, number, start_date, end_date, updated_at, "
                "daily_time_utc, daily_time_zone) "
                "VALUES (:t, 1, :d, :d, '2000-01-01', '2026-10-05T14:00:00Z', 'America/Bogota')"
            ),
            {"t": team, "d": date(2026, 10, 5)},
        )
        await connection.execute(text("UPDATE sprint SET status = 'active'"))
        updated = (
            await connection.execute(text("SELECT updated_at > '2000-01-02' FROM sprint"))
        ).scalar_one()

    assert updated is True


# ------------------------------------------------------- HU-12: the sprint number --
async def test_a_sprint_has_a_positive_number_that_is_unique_within_its_team(engine: AsyncEngine):
    team = await _a_team(engine)
    other_team = await _a_team(engine)
    dates = {"start": date(2026, 10, 5), "end": date(2026, 10, 16), "status": "closed"}
    async with engine.begin() as connection:
        await connection.execute(_SPRINT, {"team": team, "number": 1, **dates})
        # The same number in another team is another sprint number.
        await connection.execute(_SPRINT, {"team": other_team, "number": 1, **dates})

    refused = [
        (1, "sprint_number_unique"),
        (0, "sprint_number_positive"),
        (-3, "sprint_number_positive"),
    ]
    for number, constraint in refused:
        with pytest.raises(IntegrityError, match=constraint):
            async with engine.begin() as connection:
                await connection.execute(_SPRINT, {"team": team, "number": number, **dates})


async def test_a_sprint_cannot_be_stored_without_its_number(engine: AsyncEngine):
    team = await _a_team(engine)

    with pytest.raises(IntegrityError, match="not-null"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO sprint (team_id, start_date, end_date, daily_time_utc, "
                    "daily_time_zone) VALUES (:team, :d, :d, '2026-10-05T14:00:00Z', "
                    "'America/Bogota')"
                ),
                {"team": team, "d": date(2026, 10, 5)},
            )


# ------------------------------------------------------------ HU-07: the daily --
async def test_no_column_stores_a_local_date_time_or_a_time_of_day(engine: AsyncEngine):
    """DoD of HU-07 (AD-20, AD-31): instants are ``timestamptz``; a date with no time of day is
    a ``date``. No column holds a wall-clock time or a time without its offset."""
    async with engine.connect() as connection:
        local = (
            await connection.execute(
                text(
                    "SELECT table_name || '.' || column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND data_type IN ("
                    "'timestamp without time zone', 'time without time zone', "
                    "'time with time zone')"
                )
            )
        ).scalars()
        daily = (
            await connection.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'sprint' AND column_name = 'daily_time_utc'"
                )
            )
        ).scalar_one()

    assert list(local) == []
    assert daily == "timestamp with time zone"


async def test_a_sprint_needs_the_daily_time_and_a_time_zone_that_is_not_blank(
    engine: AsyncEngine,
):
    team = await _a_team(engine)
    insert = text(
        "INSERT INTO sprint (team_id, number, start_date, end_date, daily_time_utc, "
        "daily_time_zone) VALUES (:team, 1, :d, :d, :at, :zone)"
    )
    day = date(2026, 10, 5)

    with pytest.raises(IntegrityError, match="sprint_daily_time_zone_not_blank"):
        async with engine.begin() as connection:
            await connection.execute(
                insert, {"team": team, "d": day, "at": "2026-10-05T14:00:00Z", "zone": "  "}
            )
    for missing in ("at", "zone"):
        values = {"team": team, "d": day, "at": "2026-10-05T14:00:00Z", "zone": "America/Bogota"}
        with pytest.raises(IntegrityError, match="not-null"):
            async with engine.begin() as connection:
                await connection.execute(insert, {**values, missing: None})


async def _a_member(engine: AsyncEngine, team: str, email: str) -> str:
    async with engine.begin() as connection:
        user = (
            await connection.execute(
                text(
                    "INSERT INTO app_user (keycloak_subject, email, full_name) "
                    "VALUES (:sub, :email, 'Someone') RETURNING id"
                ),
                {"sub": email, "email": email},
            )
        ).scalar_one()
        await connection.execute(
            text("INSERT INTO team_member (team_id, user_id) VALUES (:team, :user)"),
            {"team": team, "user": user},
        )
    return str(user)


async def _an_active_sprint(engine: AsyncEngine, team: str) -> str:
    async with engine.begin() as connection:
        return str(
            (
                await connection.execute(
                    text(f"{_SPRINT.text} RETURNING id"),
                    {
                        "team": team,
                        "number": 1,
                        "start": date(2026, 10, 5),
                        "end": date(2026, 10, 16),
                        "status": "active",
                    },
                )
            ).scalar_one()
        )


_PARTICIPANT = text(
    "INSERT INTO sprint_participant (sprint_id, team_id, user_id, turn_order) "
    "VALUES (:sprint, :team, :user, :turn)"
)


async def test_a_participant_has_one_turn_from_one_and_no_two_share_it(engine: AsyncEngine):
    team = await _a_team(engine)
    ana = await _a_member(engine, team, "ana@example.test")
    bruno = await _a_member(engine, team, "bruno@example.test")
    sprint = await _an_active_sprint(engine, team)
    async with engine.begin() as connection:
        await connection.execute(
            _PARTICIPANT, {"sprint": sprint, "team": team, "user": ana, "turn": 1}
        )

    refused = [
        ({"user": bruno, "turn": 0}, "sprint_participant_turn_order_positive"),
        ({"user": bruno, "turn": 1}, "sprint_participant_turn_order_unique"),
        ({"user": ana, "turn": 2}, "sprint_participant_pkey"),
    ]
    for values, constraint in refused:
        with pytest.raises(IntegrityError, match=constraint):
            async with engine.begin() as connection:
                await connection.execute(_PARTICIPANT, {"sprint": sprint, "team": team, **values})


async def test_a_participant_is_a_member_of_the_very_team_of_the_sprint(engine: AsyncEngine):
    atlas, boreal = await _a_team(engine), await _a_team(engine)
    member_of_boreal = await _a_member(engine, boreal, "bea@example.test")
    sprint_of_atlas = await _an_active_sprint(engine, atlas)

    with pytest.raises(IntegrityError, match="sprint_participant_member_fk"):
        async with engine.begin() as connection:
            await connection.execute(
                _PARTICIPANT,
                {"sprint": sprint_of_atlas, "team": atlas, "user": member_of_boreal, "turn": 1},
            )
    with pytest.raises(IntegrityError, match="sprint_participant_sprint_fk"):
        async with engine.begin() as connection:
            await connection.execute(
                _PARTICIPANT,
                {"sprint": sprint_of_atlas, "team": boreal, "user": member_of_boreal, "turn": 1},
            )


async def test_deleting_a_sprint_or_its_team_deletes_its_participants(engine: AsyncEngine):
    count = text("SELECT count(*) FROM sprint_participant")
    deletes = ("DELETE FROM sprint WHERE id = :sprint", "DELETE FROM team WHERE id = :team")
    for number, delete in enumerate(deletes):
        team = await _a_team(engine)
        ana = await _a_member(engine, team, f"ana-{number}@example.test")
        sprint = await _an_active_sprint(engine, team)
        async with engine.begin() as connection:
            await connection.execute(
                _PARTICIPANT, {"sprint": sprint, "team": team, "user": ana, "turn": 1}
            )
            await connection.execute(text(delete), {"sprint": sprint, "team": team})
            assert (await connection.execute(count)).scalar_one() == 0


def test_the_migrations_go_down_and_up_again_cleanly(admin_dsn: str):
    """Downgrading removes everything the migration created, and upgrading restores it."""
    name = f"agilina_it_{uuid.uuid4().hex[:12]}"
    url = make_url(admin_dsn).set(database=name).render_as_string(hide_password=False)
    ensure_database(admin_dsn, name)
    try:
        command.upgrade(alembic_config("tenant", url), "head")
        command.downgrade(alembic_config("tenant", url), "base")

        engine = create_engine(url)
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            enums = {
                r[0]
                for r in connection.execute(text("SELECT typname FROM pg_type WHERE typtype='e'"))
            }
        engine.dispose()
        assert (
            not {
                "app_user",
                "team",
                "team_member",
                "invitation",
                "sprint",
                "sprint_participant",
                "ceremony",
            }
            & tables
        )
        assert not {"team_role", "invitation_status", "sprint_status"} & enums

        command.upgrade(alembic_config("tenant", url), "head")
    finally:
        drop_database(admin_dsn, name)


def test_the_catalog_migration_creates_the_tenant_table_and_goes_back_cleanly(admin_dsn: str):
    name = f"agilina_it_{uuid.uuid4().hex[:12]}"
    url = make_url(admin_dsn).set(database=name).render_as_string(hide_password=False)
    ensure_database(admin_dsn, name)
    try:
        command.upgrade(alembic_config("platform", url), "head")
        engine = create_engine(url)
        with engine.connect() as connection:
            columns = {c["name"] for c in inspect(connection).get_columns("tenant")}
        assert columns == {"slug", "display_name", "language", "status", "created_at"}

        command.downgrade(alembic_config("platform", url), "base")
        with engine.connect() as connection:
            assert "tenant" not in inspect(connection).get_table_names()
        engine.dispose()
    finally:
        drop_database(admin_dsn, name)


@pytest.mark.parametrize(
    "slug", ["Acme", "a", "1acme", "ac-me", "platform", "admin", "api", "x" * 40, ""]
)
async def test_the_catalog_refuses_a_slug_that_cannot_be_a_database_or_a_realm(
    platform_engine: AsyncEngine, slug: str
):
    with pytest.raises(IntegrityError, match="tenant_slug"):
        async with platform_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO tenant (slug, display_name) VALUES (:slug, 'Whatever')"),
                {"slug": slug},
            )


async def test_the_catalog_refuses_a_language_the_product_does_not_speak(
    platform_engine: AsyncEngine,
):
    with pytest.raises(IntegrityError, match="tenant_language_known"):
        async with platform_engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO tenant (slug, display_name, language) VALUES ('ab', 'Ab', 'fr')")
            )
