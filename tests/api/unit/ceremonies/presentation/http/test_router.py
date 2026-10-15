"""The worker ↔ API contract is published in the specification from the first
commit, even though its implementation arrives with HU-56."""

from httpx import AsyncClient


async def test_the_specification_publishes_the_two_worker_operations(client: AsyncClient):
    specification = (await client.get("/openapi.json")).json()

    paths = specification["paths"]
    assert "/v1/ceremonies/{ceremony_id}/context" in paths
    assert "/v1/ceremonies/{ceremony_id}/result" in paths


async def test_the_operations_declare_they_are_not_implemented_yet(client: AsyncClient):
    response = await client.get("/v1/ceremonies/8f2f0d7e-0e4c-4a2e-9a0e-0b3b1a4a1c11/context")

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


async def test_delivering_a_result_is_not_implemented_either(client: AsyncClient):
    ceremony_id = "8f2f0d7e-0e4c-4a2e-9a0e-0b3b1a4a1c11"
    result = {
        "ceremony_id": ceremony_id,
        "status": "completed",
        "started_at": "2026-10-04T14:00:00Z",
        "closed_at": "2026-10-04T14:15:00Z",
        "present_participants": [],
        "segments": [],
        "events": [],
    }

    response = await client.post(f"/v1/ceremonies/{ceremony_id}/result", json=result)

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"
