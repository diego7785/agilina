"""The name of a ceremony's LiveKit room: the one convention the API and the agent share.

The room name carries the tenant and the ceremony (AD-29), so the agent knows whom to ask for
the context before it has any. The ceremony id goes last and is read from the end, so the tenant
slug never has to be split.
"""

from uuid import UUID

_UUID_LENGTH = 36


def room_name_for(tenant: str, ceremony_id: UUID) -> str:
    """The room name of ``ceremony_id`` in ``tenant``: ``<tenant>-<ceremony_id>``."""
    return f"{tenant}-{ceremony_id}"


def parse_room_name(name: str) -> tuple[str, UUID] | None:
    """The tenant and the ceremony of a room named by ``room_name_for``, or ``None`` otherwise."""
    tenant, separator, raw_id = (
        name[: -_UUID_LENGTH - 1],
        name[-_UUID_LENGTH - 1 : -_UUID_LENGTH],
        name[-_UUID_LENGTH:],
    )
    if not tenant or separator != "-":
        return None
    try:
        ceremony_id = UUID(raw_id)
    except ValueError:
        return None
    # Only the canonical form round-trips: an uppercase id would name a different room.
    return (tenant, ceremony_id) if str(ceremony_id) == raw_id else None
