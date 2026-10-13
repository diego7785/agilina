from uuid import UUID

from pydantic import BaseModel, Field

from agilina_shared.enums import OperationMode, RoleLabel


class DashboardTeamResponse(BaseModel):
    id: UUID
    name: str
    mode: OperationMode = Field(
        description=(
            f"How Agilina works in the team: `{OperationMode.SUPPORT}` (a human Scrum Master "
            f"approves its actions) or `{OperationMode.AUTONOMOUS}`. The dashboard only shows it."
        )
    )
    label: RoleLabel = Field(
        description=(
            "The code of the label the interface shows for the role of whoever asks, derived "
            "from the role and the team's mode. It is only shown: permissions follow the role."
        )
    )
