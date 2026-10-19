"""The teams HTTP API, with in-memory doubles behind the use cases and the access ports."""

import logging
from datetime import UTC, datetime

import pytest

from agilina_api.teams.application.dtos import TeamView, UserTeamView
from agilina_api.teams.application.queries.get_active_sprint import GetActiveSprintHandler
from agilina_api.teams.presentation.http import dependencies as deps
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders import SprintBuilder, next_id
from tests.api.doubles import FakeClock, FakeSprintQueries
from tests.api.unit.teams.presentation.http.support import (
    TOKEN_ANA,
    TOKEN_BRUNO,
    TOKEN_CARLA,
    Api,
    _returning,
)


# ---------------------------------------------------------------------- create --
async def test_creating_a_team_answers_201_with_its_id_and_location(api):
    response = await api.request("POST", "", TOKEN_BRUNO, json={"name": "  Cielo  "})

    assert response.status_code == 201
    [team] = api.uow.teams.teams.values()
    assert response.json() == {"id": str(team.id)}
    assert response.headers["location"] == f"/v1/teams/{team.id}"
    assert team.name == "Cielo" and api.uow.committed is True


async def test_the_created_team_has_support_mode_english_and_its_creator_as_admin(api):
    await api.request("POST", "", TOKEN_BRUNO, json={"name": "Cielo"})

    [team] = api.uow.teams.teams.values()
    assert team.mode is OperationMode.SUPPORT and team.language is Language.EN
    membership = team.membership_of(api.bruno)
    assert membership is not None and membership.role is TeamRole.ADMIN
    assert team.created_by == api.bruno


async def test_the_creator_comes_from_the_token_not_from_the_body(api):
    response = await api.request(
        "POST", "", TOKEN_BRUNO, json={"name": "Cielo", "created_by": str(api.ana)}
    )

    assert response.status_code == 422
    assert api.uow.teams.teams == {}


@pytest.mark.parametrize("field", ["mode", "language", "role"])
async def test_the_defaults_cannot_be_chosen_in_the_body(api, field):
    response = await api.request("POST", "", TOKEN_BRUNO, json={"name": "Cielo", field: "x"})

    assert response.status_code == 422
    assert api.uow.teams.teams == {}


@pytest.mark.parametrize("name", ["", "   "])
async def test_a_blank_name_answers_422_invalid_team_name(api, name):
    response = await api.request("POST", "", TOKEN_BRUNO, json={"name": name})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_team_name"
    assert response.headers["cache-control"] == "no-store"
    assert api.uow.teams.teams == {} and api.uow.committed is False


async def test_a_name_longer_than_80_answers_422_invalid_team_name(api):
    response = await api.request("POST", "", TOKEN_BRUNO, json={"name": "x" * 81})

    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_team_name"
    assert api.uow.teams.teams == {}


async def test_a_name_of_80_characters_is_accepted(api):
    response = await api.request("POST", "", TOKEN_BRUNO, json={"name": "x" * 80})

    assert response.status_code == 201


async def test_a_body_without_a_name_answers_422(api):
    response = await api.request("POST", "", TOKEN_BRUNO, json={})

    assert response.status_code == 422
    assert api.uow.teams.teams == {}


# ------------------------------------------------------------------------ list --
async def test_listing_returns_id_name_and_role(api):
    response = await api.request("GET", "", TOKEN_ANA)

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(api.atlas),
            "name": "Atlas",
            "role": "admin",
            "mode": "support",
            "label": "scrum_master",
        },
        {
            "id": str(api.boreal),
            "name": "Boreal",
            "role": "member",
            "mode": "autonomous",
            "label": "member",
        },
    ]


async def test_the_label_of_the_same_user_is_resolved_team_by_team(api):
    cielo = next_id()
    teams = api.queries.teams_by_user[api.ana]
    api.queries.teams_by_user[api.ana] = (
        *teams,
        UserTeamView(
            team_id=cielo, name="Cielo", role=TeamRole.ADMIN, mode=OperationMode.AUTONOMOUS
        ),
    )

    response = await api.request("GET", "", TOKEN_ANA)

    assert [(team["role"], team["mode"], team["label"]) for team in response.json()] == [
        ("admin", "support", "scrum_master"),
        ("member", "autonomous", "member"),
        ("admin", "autonomous", "admin"),
    ]


async def test_a_user_without_teams_gets_an_empty_list(api):
    response = await api.request("GET", "", TOKEN_BRUNO)

    assert response.status_code == 200 and response.json() == []


# ------------------------------------------------------------------- read one --
async def test_a_member_reads_the_team_with_its_mode_language_and_role(api):
    atlas = await api.request("GET", f"/{api.atlas}", TOKEN_ANA)
    boreal = await api.request("GET", f"/{api.boreal}", TOKEN_ANA)

    assert atlas.status_code == 200
    assert atlas.json() == {
        "id": str(api.atlas),
        "name": "Atlas",
        "mode": "support",
        "language": "en",
        "role": "admin",
        "label": "scrum_master",
    }
    assert boreal.json()["role"] == "member" and boreal.json()["language"] == "es"
    assert boreal.json()["label"] == "member"


async def test_the_same_admin_is_labelled_administrator_once_the_team_is_autonomous(api):
    api.queries.views[api.atlas] = TeamView(
        team_id=api.atlas, name="Atlas", mode=OperationMode.AUTONOMOUS, language=Language.EN
    )

    response = await api.request("GET", f"/{api.atlas}", TOKEN_ANA)

    assert (response.json()["role"], response.json()["label"]) == ("admin", "admin")


async def test_a_non_member_gets_403_when_reading_a_team(api):
    response = await api.request("GET", f"/{api.atlas}", TOKEN_BRUNO)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_team_member"
    assert "Atlas" not in response.text


async def test_a_team_that_does_not_exist_answers_403_like_a_foreign_one(api):
    response = await api.request("GET", f"/{next_id()}", TOKEN_ANA)

    assert response.status_code == 403 and response.json()["error"]["code"] == "not_a_team_member"


async def test_a_member_of_a_team_that_vanished_gets_404_team_not_found(api):
    """A membership without its team cannot exist (foreign key): only a race gets here."""
    del api.queries.views[api.atlas]

    response = await api.request("GET", f"/{api.atlas}", TOKEN_ANA)

    assert response.status_code == 404 and response.json()["error"]["code"] == "team_not_found"


async def test_a_malformed_team_id_answers_422(api):
    response = await api.request("GET", "/not-a-uuid", TOKEN_ANA)

    assert response.status_code == 422


# -------------------------------------------------------------- authentication --
ROUTES = [
    ("POST", "", {"json": {"name": "Cielo"}}),
    ("GET", "", {}),
    ("GET", "/{atlas}", {}),
    ("GET", "/{atlas}/dashboard", {}),
]


@pytest.mark.parametrize(("method", "path", "kwargs"), ROUTES)
async def test_without_a_token_the_team_routes_answer_401(api, method, path, kwargs):
    response = await api.request(method, path.format(atlas=api.atlas), **kwargs)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"
    assert api.uow.teams.teams == {}


@pytest.mark.parametrize(("method", "path", "kwargs"), ROUTES)
async def test_an_invalid_token_answers_401(api, method, path, kwargs):
    response = await api.request(method, path.format(atlas=api.atlas), "forged-token", **kwargs)

    assert response.status_code == 401 and response.json()["error"]["code"] == "not_authenticated"
    assert api.uow.teams.teams == {}


async def test_without_a_token_a_blank_name_still_answers_401(api):
    response = await api.request("POST", "", json={"name": "   "})

    assert response.status_code == 401


# ---------------------------------------------------------------------- contract --
async def test_the_openapi_documents_support_and_en_as_defaults_and_the_401_422_responses(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    create = spec["paths"]["/v1/teams"]["post"]
    assert {"201", "401", "422"} <= set(create["responses"])
    assert "`support`" in create["description"] and "`en`" in create["description"]
    assert "`admin`" in create["description"]
    assert (
        "80"
        in spec["components"]["schemas"]["CreateTeamRequest"]["properties"]["name"]["description"]
    )

    assert "401" in spec["paths"]["/v1/teams"]["get"]["responses"]

    read = spec["paths"]["/v1/teams/{team_id}"]["get"]
    assert {"200", "401", "403", "422"} <= set(read["responses"])
    assert [p["name"] for p in read["parameters"]] == ["team_id"]
    team = spec["components"]["schemas"]["TeamResponse"]["properties"]
    assert "`support`" in team["mode"]["description"]
    assert "`en`" in team["language"]["description"]

    dashboard = spec["paths"]["/v1/teams/{team_id}/dashboard"]["get"]
    assert {"200", "401", "403", "404", "422"} <= set(dashboard["responses"])
    assert [p["name"] for p in dashboard["parameters"]] == ["team_id"]

    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert "ErrorEnvelope" in spec["components"]["schemas"]


def _path(api: Api, path: str) -> str:
    return path.format(atlas=api.atlas, carla=api.carla)


# -------------------------------------------------------------- sprint (HU-07) --
def _sprint_body(api: Api, **changes) -> dict:
    """Ana's sprint: 2026-10-05 to 2026-10-16, the daily at 09:00 in Bogota (sent with its
    offset), Carla speaking first. The clock is at ``NOW``, the Sunday before it starts."""
    body = {
        "start_date": "2026-10-05",
        "end_date": "2026-10-16",
        "daily_time": "2026-10-05T09:00:00-05:00",
        "time_zone": "America/Bogota",
        "participants": [str(api.carla), str(api.ana)],
    }
    return {**body, **changes}


def _active_sprint(api: Api):
    return api.members_uow.sprints.active_of(api.atlas)


async def test_an_admin_starts_the_sprint_and_gets_201_with_its_day_and_next_daily(api):
    response = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    assert response.status_code == 201
    sprint = _active_sprint(api)
    assert sprint is not None and api.members_uow.committed is True
    assert response.headers["location"] == f"/v1/teams/{api.atlas}/sprints/active"
    assert response.json() == {
        "id": str(sprint.id),
        "number": 1,
        "start_date": "2026-10-05",
        "end_date": "2026-10-16",
        "daily_time": "2026-10-05T14:00:00Z",
        "time_zone": "America/Bogota",
        "next_daily_at": "2026-10-05T14:00:00Z",
        "participants": [
            {"user_id": str(api.carla), "turn_order": 1},
            {"user_id": str(api.ana), "turn_order": 2},
        ],
        "day": {"number": 0, "total": 12, "phase": "not_started"},
    }


async def test_any_member_reads_the_active_sprint_as_it_was_saved(api):
    created = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    response = await api.request("GET", f"/{api.atlas}/sprints/active", TOKEN_CARLA)

    assert response.status_code == 200
    assert response.json() == created.json()


async def test_without_an_active_sprint_the_read_answers_200_null(api):
    await SprintBuilder().for_team_id(api.atlas).closed().saved_in(api.members_uow.sprints)

    response = await api.request("GET", f"/{api.atlas}/sprints/active", TOKEN_CARLA)

    assert response.status_code == 200
    assert response.json() is None


async def test_an_admin_edits_the_active_sprint_and_gets_it_back(api):
    sprint = await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    body = _sprint_body(
        api,
        start_date="2026-10-03",
        daily_time="2026-10-03T08:00:00+09:00",
        time_zone="Asia/Tokyo",
        participants=[str(api.ana), str(api.carla)],
    )

    response = await api.request("PUT", f"/{api.atlas}/sprints/active", TOKEN_ANA, json=body)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(sprint.id),
        "number": 1,
        "start_date": "2026-10-03",
        "end_date": "2026-10-16",
        "daily_time": "2026-10-02T23:00:00Z",
        "time_zone": "Asia/Tokyo",
        "next_daily_at": "2026-10-04T23:00:00Z",
        "participants": [
            {"user_id": str(api.ana), "turn_order": 1},
            {"user_id": str(api.carla), "turn_order": 2},
        ],
        "day": {"number": 2, "total": 14, "phase": "in_progress"},
    }
    assert api.members_uow.sprints.saved == [sprint.id] and api.members_uow.committed is True


async def test_editing_without_an_active_sprint_answers_404_no_active_sprint(api):
    response = await api.request(
        "PUT", f"/{api.atlas}/sprints/active", TOKEN_ANA, json=_sprint_body(api)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_active_sprint"
    assert api.members_uow.committed is False


async def test_a_sprint_closed_before_it_is_read_back_answers_404_no_active_sprint(api):
    """Saving and reading back are two steps: if the sprint stops being active in between
    (HU-10 will close sprints), the answer says so instead of failing."""
    api.app.dependency_overrides[deps.get_get_active_sprint_handler] = _returning(
        GetActiveSprintHandler(FakeSprintQueries(), FakeClock())
    )

    response = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "no_active_sprint"


@pytest.mark.parametrize(("method", "path"), [("POST", "sprints"), ("PUT", "sprints/active")])
async def test_configuring_the_sprint_of_a_team_that_vanished_answers_404_team_not_found(
    api, method, path
):
    """A membership without its team cannot exist (foreign key): only a race gets here."""
    del api.members_uow.teams.teams[api.atlas]

    response = await api.request(method, f"/{api.atlas}/{path}", TOKEN_ANA, json=_sprint_body(api))

    assert response.status_code == 404 and response.json()["error"]["code"] == "team_not_found"


@pytest.mark.parametrize(
    "changes",
    [
        {"daily_time": "2026-10-05T09:00:00"},  # no offset: not an instant
        {"daily_time": "09:00"},
        {"start_date": "2026-10-05T09:00:00Z"},  # a date, not an instant
        {"end_date": "16/10/2026"},
        {"participants": ["not-a-uuid"]},
        {"participants": None},
        {"time_zone": None},
        {"status": "closed"},  # unknown fields are refused, not ignored
        {"team_id": "x"},
    ],
)
async def test_a_malformed_sprint_answers_422_validation_error_and_stores_nothing(api, changes):
    response = await api.request(
        "POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api, **changes)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert api.members_uow.sprints.sprints == {} and api.members_uow.committed is False


@pytest.mark.parametrize("missing", ["start_date", "end_date", "daily_time", "time_zone"])
async def test_an_edit_missing_a_field_answers_422_and_changes_nothing(api, missing):
    sprint = await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    body = _sprint_body(api)
    del body[missing]

    response = await api.request("PUT", f"/{api.atlas}/sprints/active", TOKEN_ANA, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert api.members_uow.sprints.saved == [] and _active_sprint(api) == sprint


SPRINT_WRITES = [("POST", "/{atlas}/sprints"), ("PUT", "/{atlas}/sprints/active")]
SPRINT_ROUTES = [*SPRINT_WRITES, ("GET", "/{atlas}/sprints/active")]


def _rule_breaking_body(api: Api, rule: str) -> dict:
    """A sprint body that breaks one of the rules of the domain, and only that one."""
    changes = {
        "sprint_ends_before_start": {"start_date": "2026-10-16", "end_date": "2026-10-15"},
        "invalid_time_zone": {"time_zone": "Mars/Olympus"},
        "no_daily_participants": {"participants": []},
        "duplicate_daily_participant": {"participants": [str(api.carla), str(api.carla)]},
        # Bruno has an account but is not a member of Atlas.
        "daily_participant_not_a_member": {"participants": [str(api.ana), str(api.bruno)]},
    }[rule]
    return _sprint_body(api, **changes)


SPRINT_RULES = [
    "sprint_ends_before_start",
    "invalid_time_zone",
    "no_daily_participants",
    "duplicate_daily_participant",
    "daily_participant_not_a_member",
]


@pytest.mark.parametrize("rule", SPRINT_RULES)
async def test_starting_a_sprint_that_breaks_a_rule_answers_422_with_its_code(api, rule):
    response = await api.request(
        "POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_rule_breaking_body(api, rule)
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert set(error) == {"status", "code", "message", "request_id"}
    assert (error["status"], error["code"]) == (422, rule)
    assert api.members_uow.sprints.sprints == {} and api.members_uow.committed is False


@pytest.mark.parametrize("rule", SPRINT_RULES)
async def test_an_edit_that_breaks_a_rule_answers_422_with_its_code_and_changes_nothing(api, rule):
    sprint = await (
        SprintBuilder()
        .for_team_id(api.atlas)
        .with_participants(api.ana)
        .saved_in(api.members_uow.sprints)
    )

    response = await api.request(
        "PUT", f"/{api.atlas}/sprints/active", TOKEN_ANA, json=_rule_breaking_body(api, rule)
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert set(error) == {"status", "code", "message", "request_id"}
    assert (error["status"], error["code"]) == (422, rule)
    stored = _active_sprint(api)
    assert stored is not None and stored.participants == (api.ana,)
    assert (stored.period, stored.daily_time) == (sprint.period, sprint.daily_time)
    assert api.members_uow.sprints.saved == [] and api.members_uow.committed is False


@pytest.mark.parametrize(("method", "path"), SPRINT_WRITES)
async def test_a_refused_sprint_does_not_echo_what_was_sent(api, method, path):
    """The message and the details are the catalog's: the values sent are not repeated."""
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    body = _sprint_body(api, time_zone="Europe/Atlantis", participants=[str(api.bruno)])

    zone = await api.request(method, _path(api, path), TOKEN_ANA, json=body)
    outsider = await api.request(
        method, _path(api, path), TOKEN_ANA, json=_sprint_body(api, participants=[str(api.bruno)])
    )

    assert zone.json()["error"]["code"] == "invalid_time_zone"
    assert outsider.json()["error"]["code"] == "daily_participant_not_a_member"
    assert "Atlantis" not in zone.text and str(api.bruno) not in outsider.text


async def test_a_sprint_may_start_and_end_on_the_same_day(api):
    body = _sprint_body(api, start_date="2026-10-10", end_date="2026-10-10")

    response = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=body)

    assert response.status_code == 201
    assert response.json()["day"] == {"number": 0, "total": 1, "phase": "not_started"}


async def test_starting_a_second_active_sprint_answers_409_active_sprint_exists(api):
    first = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))
    api.members_uow.active_sprints.teams_with_active_sprint.add(api.atlas)
    api.members_uow.committed = False

    response = await api.request(
        "POST",
        f"/{api.atlas}/sprints",
        TOKEN_ANA,
        json=_sprint_body(api, participants=[str(api.ana)]),
    )

    assert first.status_code == 201
    assert response.status_code == 409
    error = response.json()["error"]
    assert set(error) == {"status", "code", "message", "request_id"}
    assert error["code"] == "active_sprint_exists"
    assert len(api.members_uow.sprints.sprints) == 1 and api.members_uow.committed is False
    active = _active_sprint(api)
    assert active is not None and active.participants == (api.carla, api.ana)


async def test_a_member_in_the_daily_who_is_removed_leaves_it_and_the_turns_close_up(api):
    await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    removed = await api.users("DELETE", f"/{api.carla}", TOKEN_ANA)
    read = await api.request("GET", f"/{api.atlas}/sprints/active", TOKEN_ANA)

    assert removed.status_code == 204
    assert read.json()["participants"] == [{"user_id": str(api.ana), "turn_order": 1}]


async def test_the_admin_of_the_token_is_who_started_the_sprint_in_the_log(api, caplog):
    with caplog.at_level(logging.INFO):
        await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    assert f"Team {api.atlas}: user {api.ana} started sprint" in caplog.text


async def test_the_admin_of_the_token_is_who_edited_the_sprint_in_the_log(api, caplog):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    with caplog.at_level(logging.INFO):
        await api.request("PUT", f"/{api.atlas}/sprints/active", TOKEN_ANA, json=_sprint_body(api))

    assert f"Team {api.atlas}: user {api.ana} reconfigured sprint" in caplog.text


@pytest.mark.parametrize(("method", "path"), SPRINT_WRITES)
async def test_a_member_who_is_not_an_admin_cannot_configure_the_sprint(api, method, path):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    response = await api.request(
        method, _path(api, path), TOKEN_CARLA, json=_sprint_body(api, participants=[])
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_team_admin"
    assert api.members_uow.sprints.saved == [] and api.members_uow.committed is False
    assert len(api.members_uow.sprints.sprints) == 1


@pytest.mark.parametrize(("method", "path"), SPRINT_ROUTES)
async def test_someone_outside_the_team_cannot_reach_its_sprint(api, method, path):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    response = await api.request(method, _path(api, path), TOKEN_BRUNO, json=_sprint_body(api))

    assert response.status_code == 403 and response.json()["error"]["code"] == "not_a_team_member"
    assert str(api.carla) not in response.text
    assert api.members_uow.committed is False


@pytest.mark.parametrize(("method", "path"), SPRINT_ROUTES)
async def test_without_a_valid_token_the_sprint_routes_answer_401(api, method, path):
    missing = await api.request(method, _path(api, path), json=_sprint_body(api))
    forged = await api.request(method, _path(api, path), "forged-token", json=_sprint_body(api))

    for response in (missing, forged):
        assert (
            response.status_code == 401 and response.json()["error"]["code"] == "not_authenticated"
        )
    assert api.members_uow.sprints.sprints == {}


async def test_the_openapi_documents_the_sprint_routes_and_their_errors(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    create = spec["paths"]["/v1/teams/{team_id}/sprints"]["post"]
    active = spec["paths"]["/v1/teams/{team_id}/sprints/active"]
    # 400 and the 404 of the tenant come with every signed-in route (AD-29).
    assert set(create["responses"]) == {"201", "400", "401", "403", "404", "409", "422", "500"}
    assert set(active["get"]["responses"]) == {"200", "400", "401", "403", "404", "422", "500"}
    assert set(active["put"]["responses"]) == {"200", "400", "401", "403", "404", "422", "500"}
    assert "`not_a_team_admin`" in create["responses"]["403"]["description"]
    assert "`no_active_sprint`" in active["put"]["responses"]["404"]["description"]
    assert "`team_not_found`" in active["put"]["responses"]["404"]["description"]
    assert "`not_a_team_member`" in active["get"]["responses"]["403"]["description"]
    for operation in (create, active["get"], active["put"]):
        assert [p["name"] for p in operation["parameters"]] == ["team_id"]
    schemas = spec["components"]["schemas"]
    assert set(schemas["SprintDayResponse"]["properties"]) == {"number", "total", "phase"}
    assert schemas["SprintRequest"]["additionalProperties"] is False


async def test_the_openapi_documents_each_rule_of_the_sprint_with_its_code(api):
    async with api.client() as client:
        spec = (await client.get("/openapi.json")).json()

    create = spec["paths"]["/v1/teams/{team_id}/sprints"]["post"]
    edit = spec["paths"]["/v1/teams/{team_id}/sprints/active"]["put"]
    for operation in (create, edit):
        refused = operation["responses"]["422"]["description"]
        assert all(f"`{code}`" in refused for code in SPRINT_RULES)
        assert all(f"`{code}`" in operation["description"] for code in SPRINT_RULES)
    assert "`active_sprint_exists`" in create["responses"]["409"]["description"]
    assert "409" not in edit["responses"]
    request = spec["components"]["schemas"]["SprintRequest"]
    assert all(f"`{code}`" in request["description"] for code in SPRINT_RULES)
    member = spec["paths"]["/v1/users/{user_id}"]["delete"]
    assert "daily" in member["description"]


# ------------------------------------------------------- sprint number (HU-12) --
async def test_the_first_sprint_of_a_team_is_number_1(api):
    response = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    assert response.status_code == 201 and response.json()["number"] == 1


async def test_a_new_sprint_takes_the_highest_number_of_the_team_plus_one(api):
    await (
        SprintBuilder()
        .for_team_id(api.atlas)
        .numbered(4)
        .closed()
        .saved_in(api.members_uow.sprints)
    )

    response = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    assert response.status_code == 201 and response.json()["number"] == 5


async def test_the_number_of_the_sprint_is_the_same_wherever_it_is_read_and_after_editing(api):
    created = await api.request("POST", f"/{api.atlas}/sprints", TOKEN_ANA, json=_sprint_body(api))

    read = await api.request("GET", f"/{api.atlas}/sprints/active", TOKEN_CARLA)
    edited = await api.request(
        "PUT",
        f"/{api.atlas}/sprints/active",
        TOKEN_ANA,
        json=_sprint_body(api, end_date="2026-10-20"),
    )
    dashboard = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)

    numbers = [
        created.json()["number"],
        read.json()["number"],
        edited.json()["number"],
        dashboard.json()["sprint"]["number"],
    ]
    assert numbers == [1, 1, 1, 1]


@pytest.mark.parametrize(("method", "path"), SPRINT_WRITES)
async def test_the_number_cannot_be_sent_by_the_client(api, method, path):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    response = await api.request(
        method, _path(api, path), TOKEN_ANA, json=_sprint_body(api, number=7)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "7" not in response.json()["error"]["message"]


# ------------------------------------------------------------- dashboard (HU-12) --
def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


async def test_an_admin_reads_the_dashboard_of_a_team_whose_sprint_has_not_started(api):
    """The default sprint runs 2026-10-05 to 2026-10-16 with the daily at 09:00 in Bogota
    (14:00 UTC); the clock is at ``NOW``, the Sunday before it starts."""
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    assert response.status_code == 200
    assert response.json() == {
        "team": {
            "id": str(api.atlas),
            "name": "Atlas",
            "mode": "support",
            "label": "scrum_master",
        },
        "sprint": {
            "number": 1,
            "start_date": "2026-10-05",
            "end_date": "2026-10-16",
            "day": {"number": 0, "total": 12, "phase": "not_started"},
        },
        "next_ceremony": {
            "type": "daily",
            "starts_at": "2026-10-05T14:00:00Z",
            "join_opens_at": "2026-10-05T13:50:00Z",
            "join_closes_at": "2026-10-05T14:15:00Z",
        },
        "can_configure": True,
    }


async def test_a_member_gets_the_same_dashboard_without_the_settings_entry(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)

    admin = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)
    member = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)

    assert member.status_code == 200
    assert member.json()["can_configure"] is False
    assert member.json()["team"]["label"] == "member"
    assert member.json()["sprint"] == admin.json()["sprint"]
    assert member.json()["next_ceremony"] == admin.json()["next_ceremony"]


async def test_while_the_sprint_is_in_progress_it_shows_the_day_and_the_next_daily(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(7, 15)  # after the daily of Wednesday the 7th

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)

    assert response.json()["sprint"]["day"] == {"number": 3, "total": 12, "phase": "in_progress"}
    assert response.json()["next_ceremony"] == {
        "type": "daily",
        "starts_at": "2026-10-08T14:00:00Z",
        "join_opens_at": "2026-10-08T13:50:00Z",
        "join_closes_at": "2026-10-08T14:15:00Z",
    }


async def test_the_daily_that_starts_in_ten_minutes_has_its_room_open_right_now(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(7, 13, 50)

    ceremony = (await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)).json()[
        "next_ceremony"
    ]

    assert ceremony["join_opens_at"] == "2026-10-07T13:50:00Z"
    assert ceremony["starts_at"] == "2026-10-07T14:00:00Z"


async def test_a_daily_under_way_stays_joinable_for_whoever_arrives_late(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(7, 14, 14)

    ceremony = (await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)).json()[
        "next_ceremony"
    ]

    assert ceremony["starts_at"] == "2026-10-07T14:00:00Z"
    assert ceremony["join_closes_at"] == "2026-10-07T14:15:00Z"


async def test_once_its_window_closed_the_dashboard_moves_on_to_the_next_daily(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(7, 14, 15)

    ceremony = (await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)).json()[
        "next_ceremony"
    ]

    assert ceremony["starts_at"] == "2026-10-08T14:00:00Z"


async def test_a_team_without_an_active_sprint_has_no_sprint_and_no_ceremony(api):
    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_CARLA)

    assert response.status_code == 200
    assert response.json() == {
        "team": {"id": str(api.atlas), "name": "Atlas", "mode": "support", "label": "member"},
        "sprint": None,
        "next_ceremony": None,
        "can_configure": False,
    }


async def test_a_closed_sprint_does_not_count_as_the_active_one(api):
    await SprintBuilder().for_team_id(api.atlas).closed().saved_in(api.members_uow.sprints)

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    assert response.json()["sprint"] is None and response.json()["next_ceremony"] is None


async def test_once_the_last_daily_started_the_sprint_stays_but_there_is_no_next_ceremony(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(16, 15)

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    assert response.json()["sprint"]["day"] == {"number": 12, "total": 12, "phase": "in_progress"}
    assert response.json()["next_ceremony"] is None


async def test_a_finished_sprint_that_is_still_open_has_no_next_ceremony(api):
    await SprintBuilder().for_team_id(api.atlas).saved_in(api.members_uow.sprints)
    api.clock.current = _at(18, 12)

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    assert response.json()["sprint"]["day"]["phase"] == "finished"
    assert response.json()["next_ceremony"] is None


async def test_the_label_of_the_admin_follows_the_mode_of_the_team(api):
    api.queries.views[api.atlas] = TeamView(
        team_id=api.atlas, name="Atlas", mode=OperationMode.AUTONOMOUS, language=Language.EN
    )

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    team = response.json()["team"]
    assert (team["mode"], team["label"]) == ("autonomous", "admin")
    assert response.json()["can_configure"] is True


async def test_a_non_member_gets_403_when_reading_a_dashboard(api):
    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_BRUNO)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_team_member"
    assert "Atlas" not in response.text


async def test_a_dashboard_of_a_team_that_does_not_exist_answers_403_like_a_foreign_one(api):
    response = await api.request("GET", f"/{next_id()}/dashboard", TOKEN_ANA)

    assert response.status_code == 403 and response.json()["error"]["code"] == "not_a_team_member"


async def test_a_member_of_a_team_that_vanished_gets_404_team_not_found_on_the_dashboard(api):
    """A membership without its team cannot exist (foreign key): only a race gets here."""
    del api.queries.views[api.atlas]

    response = await api.request("GET", f"/{api.atlas}/dashboard", TOKEN_ANA)

    assert response.status_code == 404 and response.json()["error"]["code"] == "team_not_found"


async def test_a_malformed_team_id_on_the_dashboard_answers_422(api):
    response = await api.request("GET", "/not-a-uuid/dashboard", TOKEN_ANA)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
