"""Domain models and contract shared by the Agilina deployables.

This package is the reason Agilina lives in a single repository: the contract
between the worker and the API is expressed as shared types instead of
documentation that goes stale (architecture document, section 5.2). The pure rules
that several deployables must compute the same way live here too, in their own
subpackages (``sprint_calendar``).
"""

from agilina_shared.contract import (
    CeremonyContext,
    CeremonyEvent,
    CeremonyResult,
    ParticipantContext,
    ResultReceipt,
    TranscriptSegment,
)
from agilina_shared.enums import (
    CeremonyEventType,
    CeremonyStatus,
    CeremonyType,
    Language,
    OperationMode,
    RoleLabel,
    TeamRole,
)
from agilina_shared.role_label import role_label
from agilina_shared.room_name import parse_room_name, room_name_for

__all__ = [
    "CONTRACT_VERSION",
    "CeremonyContext",
    "CeremonyEvent",
    "CeremonyEventType",
    "CeremonyResult",
    "CeremonyStatus",
    "CeremonyType",
    "Language",
    "OperationMode",
    "ParticipantContext",
    "ResultReceipt",
    "RoleLabel",
    "TeamRole",
    "TranscriptSegment",
    "parse_room_name",
    "role_label",
    "room_name_for",
]

CONTRACT_VERSION = "3.0"
"""Worker ↔ API contract version.

Changing it is a BREAKING CHANGE and must be declared in the commit footer
(Avance 1 document, section 7.3). 2.0: field names and enum values moved to
English; nothing was deployed with 1.0. 3.0: the context carries the tenant and the
sprint, ``turn_order`` starts at 1 and the result carries the ceremony events (AGI-64).
"""
