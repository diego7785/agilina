"""The room name is the one convention the API and the agent share: the agent reads tenant and
ceremony from it before it has any context."""

from uuid import UUID

import pytest

from agilina_shared import parse_room_name, room_name_for
from tests.shared.builders import next_id

CEREMONY_ID = UUID("0b6c1f4e-8a52-4f0e-9d4b-6a1f2c3d4e5f")


def test_the_room_is_named_after_tenant_and_ceremony():
    assert room_name_for("acme", CEREMONY_ID) == "acme-0b6c1f4e-8a52-4f0e-9d4b-6a1f2c3d4e5f"


@pytest.mark.parametrize("tenant", ["acme", "ecomoda", "acme-latam-2"])
def test_parsing_a_room_name_gives_back_tenant_and_ceremony(tenant: str):
    """A slug may have hyphens: the ceremony is read from the end, so it is never split."""
    ceremony_id = next_id()

    assert parse_room_name(room_name_for(tenant, ceremony_id)) == (tenant, ceremony_id)


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param("ceremony-1", id="too short"),
        pytest.param(str(CEREMONY_ID), id="no tenant"),
        pytest.param(f"-{CEREMONY_ID}", id="empty tenant"),
        pytest.param(f"acme_{CEREMONY_ID}", id="no hyphen before the ceremony"),
        pytest.param("acme-" + "z" * 36, id="not a uuid"),
        pytest.param(f"acme-{str(CEREMONY_ID).upper()}", id="uppercase uuid"),
        pytest.param("acme-0b6c1f4e8a52-4f0e-9d4b-6a1f-2c3d4e5f", id="hyphens out of place"),
    ],
)
def test_a_room_not_named_by_the_convention_is_not_parsed(name: str):
    assert parse_room_name(name) is None
