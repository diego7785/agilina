"""Automatic outputs of the system: the summary Excel in OneDrive and a Slack DM per member.

Agilina always produces them, without approval and in every mode. Their destinations come
from the team configuration (``onedrive_folder`` and each member's ``slack_user``), never from
the model: the model only provides the content (the final summary and action items). They do
not go through the output guard and are not evaluated as an injection effect; a tampered
summary (c03, c05) is already measured on ``summary`` and these outputs spread it to the
whole team. Like the simulated tools, they open no network connection and write no files.
"""

import logging
from typing import Final

from purple_team.core.models import CeremonyOutput
from purple_team.team_context import TeamContext
from purple_team.tools.base import SIMULATED_STATUS, SystemChannel, SystemOutputRecord

EXCEL_PREFIX: Final = "resumen-"
EXCEL_SUFFIX: Final = ".xlsx"
EXCEL_SHEET: Final = "Resumen"
EXCEL_OPERATION: Final = "upload_workbook"
DM_OPERATION: Final = "send_direct_message"
EXCEL_CONFIGURED_BY: Final = "team_context.onedrive_folder"

_LOGGER = logging.getLogger(__name__)


class SystemOutputs:
    """Outputs Agilina always produces, without approval.

    Their destinations come from the team configuration, never from the model; the model
    only provides the content. Every member receives the same summary (the harness has no
    per-member content: a documented simplification of the "individual summary").
    """

    def __init__(self, team_context: TeamContext) -> None:
        self._team_context = team_context

    def deliver(self, output: CeremonyOutput, case_id: str) -> tuple[SystemOutputRecord, ...]:
        """Excel first, then one direct message per member in the order of the file.

        ``output`` is the final output (after the output guard), so the Excel never lists a
        blocked item. The file name is derived by the system from ``case_id`` (which stands
        for the date and ceremony Agilina would use; it follows ``CASE_ID_PATTERN`` of
        ``cases.py``, lowercase letters, digits and hyphens only, so the path cannot leave the
        folder).
        """
        context = self._team_context
        excel = SystemOutputRecord(
            sequence=1,
            channel=SystemChannel.ONEDRIVE_EXCEL,
            operation=EXCEL_OPERATION,
            destination=f"{context.onedrive_folder}{EXCEL_PREFIX}{case_id}{EXCEL_SUFFIX}",
            configured_by=EXCEL_CONFIGURED_BY,
            payload={
                "sheet": EXCEL_SHEET,
                "summary": output.summary,
                "action_items": [item.to_dict() for item in output.action_items],
            },
            status=SIMULATED_STATUS,
        )
        messages = tuple(
            SystemOutputRecord(
                sequence=index + 2,
                channel=SystemChannel.SLACK_DM,
                operation=DM_OPERATION,
                destination=member.slack_user,
                configured_by=f"team_context.members[{index}].slack_user",
                payload={"text": output.summary},
                status=SIMULATED_STATUS,
            )
            for index, member in enumerate(context.members)
        )
        records = (excel, *messages)
        for record in records:
            _LOGGER.info("SIMULATED %s %s", record.operation, record.destination)
        return records
