"""The permission matrix: every route of a team declares the role it needs (HU-04).

``docs/permisos.md`` is the reference for people; this inventory is what the code is held to.
A route added tomorrow fails here until someone decides, on purpose, which role it needs.
"""

import ast
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from agilina_api.ceremonies.presentation.http import dailies_router
from agilina_api.identity.presentation.http import router as identity_router
from agilina_api.shared.presentation.http.access import (
    current_team_admin,
    current_team_admin_by_query,
    current_team_member,
    current_team_member_by_query,
    current_user_id,
)
from agilina_api.teams.presentation.http import router as teams_router
from agilina_api.teams.presentation.http import users_router

ROOT = Path(__file__).parents[4]
USER, MEMBER, ADMIN = "usuario", "miembro", "admin"

# The role each route of the teams needs. Authorization looks at the internal role.
NEEDED_ROLE = {
    ("post", "/v1/teams"): USER,
    ("get", "/v1/teams"): USER,
    ("get", "/v1/teams/{team_id}"): MEMBER,
    ("get", "/v1/teams/{team_id}/dashboard"): MEMBER,
    ("post", "/v1/teams/{team_id}/sprints"): ADMIN,
    ("get", "/v1/teams/{team_id}/sprints/active"): MEMBER,
    ("put", "/v1/teams/{team_id}/sprints/active"): ADMIN,
    # A member, and on top of it a participant of the daily: a rule of the use case (AGI-59).
    ("post", "/v1/teams/{team_id}/dailies/current/token"): MEMBER,
    ("get", "/v1/users/me"): MEMBER,
    ("get", "/v1/users"): ADMIN,
    ("get", "/v1/users/{user_id}"): ADMIN,
    ("patch", "/v1/users/{user_id}"): ADMIN,
    ("delete", "/v1/users/{user_id}"): ADMIN,
    ("post", "/v1/users/invitations"): ADMIN,
}
# The same dependencies, for the routes that name the team in ``?team_id=``.
REQUIRED_BY = {
    USER: (current_user_id,),
    MEMBER: (current_team_member, current_team_member_by_query),
    ADMIN: (current_team_admin, current_team_admin_by_query),
}


def _calls(dependant) -> set:
    found = {dependant.call}
    for child in dependant.dependencies:
        found |= _calls(child)
    return found


def _routes() -> dict[tuple[str, str], APIRoute]:
    # The routers, not the application: the application wraps what it includes.
    routes = [
        *teams_router.router.routes,
        *users_router.router.routes,
        *identity_router.team_invitations_router.routes,
        *dailies_router.router.routes,
    ]
    return {
        (method.lower(), route.path): route
        for route in routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def _team_routes() -> list[tuple[str, str]]:
    return sorted(key for key in _routes() if key[1].startswith(("/v1/teams", "/v1/users")))


def test_every_route_of_the_teams_is_in_the_inventory_and_the_inventory_has_no_ghost():
    assert set(_team_routes()) == set(NEEDED_ROLE)


@pytest.mark.parametrize("operation", sorted(NEEDED_ROLE), ids=str)
def test_a_route_asks_for_exactly_the_role_the_inventory_says(operation):
    calls = _calls(_routes()[operation].dependant)

    asked = {
        role
        for role, dependencies in REQUIRED_BY.items()
        if any(dependency in calls for dependency in dependencies)
    }
    # ``current_team_admin`` is built on ``current_team_member`` and that on ``current_user_id``:
    # a stronger dependency brings the weaker ones with it.
    strongest = ADMIN if ADMIN in asked else MEMBER if MEMBER in asked else USER
    assert strongest == NEEDED_ROLE[operation]


def _matrix_of_the_doc() -> dict[tuple[str, str], tuple[str, str, str]]:
    doc = (ROOT / "docs" / "permisos.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\| .+? \| `(GET|POST|PUT|PATCH|DELETE) (\S+)` \| (\w+) \| (✅|❌) \| (✅|❌) \|$",
        doc,
        flags=re.MULTILINE,
    )
    return {
        (method.lower(), path): (needed, member, admin)
        for method, path, needed, member, admin in rows
    }


def test_the_matrix_of_the_doc_is_the_inventory():
    documented = _matrix_of_the_doc()

    assert set(documented) == set(NEEDED_ROLE)
    for operation, needed in NEEDED_ROLE.items():
        doc_needed, member_can, admin_can = documented[operation]
        assert doc_needed == needed
        assert admin_can == "✅"
        assert (member_can == "✅") == (needed in (USER, MEMBER))


# --------------------------------------------------- the label never authorizes --
SRC = ROOT / "api" / "src" / "agilina_api"
# Where the label may be read: the places that build what the interface shows.
READ_SIDE = ("/presentation/", "/application/dtos/", "/application/queries/")


def _imports_the_label(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("agilina_shared")
        ):
            if any(alias.name in {"role_label", "RoleLabel"} for alias in node.names):
                return True
    return False


def test_only_the_read_side_imports_the_label():
    importers = [path for path in SRC.rglob("*.py") if _imports_the_label(path)]

    assert importers, "the label is used somewhere"
    outside = [
        str(path.relative_to(SRC))
        for path in importers
        if not any(side in path.as_posix() for side in READ_SIDE)
    ]
    assert outside == []
