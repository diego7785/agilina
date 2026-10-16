"""Domain enumerations.

The values are the ones that travel through the API and are stored in the
database (they match the PostgreSQL enum types). The label shown for a role is not
an enum of the database: ``role_label`` derives it from the role and the team's mode.
"""

from agilina_shared.enums.ceremony_event_type import CeremonyEventType
from agilina_shared.enums.ceremony_status import CeremonyStatus
from agilina_shared.enums.ceremony_type import CeremonyType
from agilina_shared.enums.language import Language
from agilina_shared.enums.operation_mode import OperationMode
from agilina_shared.enums.role_label import RoleLabel
from agilina_shared.enums.team_role import TeamRole

__all__ = [
    "CeremonyEventType",
    "CeremonyStatus",
    "CeremonyType",
    "Language",
    "OperationMode",
    "RoleLabel",
    "TeamRole",
]
