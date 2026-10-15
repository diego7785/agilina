"""With the real wiring, nothing opens without a tenant and a session (HU-03, AD-29)."""

import pytest
from httpx import AsyncClient

from agilina_api.bootstrap.app import create_app
from agilina_api.shared.presentation.http.tenancy import TENANT_HEADER
from tests.api.builders import next_id

# What is open on purpose, with the reason. A route added tomorrow is closed until someone
# decides here, on purpose, that it is not.
#
# The platform's own: they need neither a tenant nor a session.
NO_TENANT = {
    ("get", "/health"): "liveness probe",
    ("get", "/health/ready"): "readiness probe",
    ("post", "/v1/ceremonies/{ceremony_id}/result"): "worker contract, not implemented (HU-55)",
}
# A tenant's, but with no session: the person invited has no account yet.
TENANT_ONLY = {
    ("get", "/v1/tenant"): "the web asks if the organization exists before signing anybody in",
    ("post", "/v1/invitations/status"): "the invited person has no account yet",
    ("post", "/v1/invitations/activate"): "the invited person has no account yet",
    ("post", "/v1/invitations/request-new"): "the invited person has no account yet",
}


def _operations() -> list[tuple[str, str]]:
    paths = create_app().openapi()["paths"]
    return [(method, path) for path, methods in paths.items() for method in methods]


def _url(path: str) -> str:
    return (
        path.replace("{team_id}", str(next_id()))
        .replace("{user_id}", str(next_id()))
        .replace("{ceremony_id}", str(next_id()))
    )


def test_the_open_routes_are_routes_that_exist():
    assert set(NO_TENANT) | set(TENANT_ONLY) <= set(_operations())


@pytest.mark.parametrize(
    ("method", "path"), [op for op in _operations() if op not in NO_TENANT], ids=str
)
async def test_every_route_of_a_tenant_answers_400_without_one(client: AsyncClient, method, path):
    response = await client.request(method, _url(path))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "tenant_required"


@pytest.mark.parametrize(
    ("method", "path"),
    [op for op in _operations() if op not in NO_TENANT and op not in TENANT_ONLY],
    ids=str,
)
async def test_every_route_that_needs_a_session_answers_401_without_a_token(
    client: AsyncClient, method, path
):
    response = await client.request(method, _url(path), headers={TENANT_HEADER: "acme"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "token", ["", "anything", "Bearer abc", "eyJhbGciOiJSUzI1NiJ9.e30.signature", "a.b.c"]
)
async def test_a_token_that_is_not_one_of_keycloak_answers_401(client: AsyncClient, token):
    response = await client.get(
        "/v1/teams", headers={"Authorization": f"Bearer {token}", TENANT_HEADER: "acme"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
