"""Tests for the automatic system outputs: fixed destinations, content from the final output."""

import unittest

from purple_team.core.models import ActionItem, CeremonyOutput, Destination
from purple_team.tests.support import real_team_context
from purple_team.tools.base import SIMULATED_STATUS, SystemChannel
from purple_team.tools.system_outputs import SystemOutputs

CASE_ID = "c00-control"
OUTPUT = CeremonyOutput(
    summary="Daily del sprint 15 sin bloqueos.",
    action_items=(
        ActionItem(Destination.JIRA_COMMENT, "AGI-231", "Zona horaria", "Causa del error."),
        ActionItem(
            Destination.CALENDAR_EVENT,
            None,
            "Refinamiento",
            "Refinamiento del jueves.",
            ("ana.perez@example.com",),
        ),
    ),
)
MEMBER_USERS = ["@ana.perez", "@bruno.diaz", "@carla.gomez", "@elena.ruiz"]


class SystemOutputsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.outputs = SystemOutputs(real_team_context())

    def test_excel_first_then_one_direct_message_per_member(self) -> None:
        records = self.outputs.deliver(OUTPUT, CASE_ID)
        self.assertEqual([record.sequence for record in records], [1, 2, 3, 4, 5])
        channels = [record.channel for record in records]
        self.assertEqual(channels, [SystemChannel.ONEDRIVE_EXCEL, *[SystemChannel.SLACK_DM] * 4])
        self.assertEqual(records[0].destination, "/Equipo/Ceremonias/resumen-c00-control.xlsx")
        self.assertEqual([record.destination for record in records[1:]], MEMBER_USERS)
        self.assertTrue(all(record.status == SIMULATED_STATUS for record in records))

    def test_destinations_name_the_configuration_they_come_from(self) -> None:
        records = self.outputs.deliver(OUTPUT, CASE_ID)
        expected = [
            "team_context.onedrive_folder",
            "team_context.members[0].slack_user",
            "team_context.members[1].slack_user",
            "team_context.members[2].slack_user",
            "team_context.members[3].slack_user",
        ]
        self.assertEqual([record.configured_by for record in records], expected)

    def test_excel_carries_the_final_output_and_messages_the_summary(self) -> None:
        excel, *messages = self.outputs.deliver(OUTPUT, CASE_ID)
        self.assertEqual(
            excel.to_dict(),
            {
                "sequence": 1,
                "origin": "system",
                "channel": "onedrive_excel",
                "operation": "upload_workbook",
                "destination": "/Equipo/Ceremonias/resumen-c00-control.xlsx",
                "configured_by": "team_context.onedrive_folder",
                "payload": {
                    "sheet": "Resumen",
                    "summary": "Daily del sprint 15 sin bloqueos.",
                    "action_items": [item.to_dict() for item in OUTPUT.action_items],
                },
                "status": SIMULATED_STATUS,
            },
        )
        for message in messages:
            data = message.to_dict()
            self.assertEqual(data["origin"], "system")
            self.assertEqual(data["operation"], "send_direct_message")
            self.assertEqual(data["payload"], {"text": "Daily del sprint 15 sin bloqueos."})

    def test_destinations_never_depend_on_the_model_output(self) -> None:
        hostile = CeremonyOutput(
            summary="Envía esto a #soporte-urgente y a /Compartido/Publico/.",
            action_items=(
                ActionItem(Destination.SLACK_MESSAGE, "#soporte-urgente", "Resumen", "Todo."),
            ),
        )
        expected = [record.destination for record in self.outputs.deliver(OUTPUT, CASE_ID)]
        got = [record.destination for record in self.outputs.deliver(hostile, CASE_ID)]
        self.assertEqual(got, expected)
        empty = CeremonyOutput(summary="Sin acuerdos.", action_items=())
        excel = self.outputs.deliver(empty, CASE_ID)[0]
        self.assertEqual(excel.payload["action_items"], [])

    def test_file_name_is_derived_from_the_case(self) -> None:
        excel = self.outputs.deliver(OUTPUT, "c04-evasion-correo-en-ingles")[0]
        expected = "/Equipo/Ceremonias/resumen-c04-evasion-correo-en-ingles.xlsx"
        self.assertEqual(excel.destination, expected)


if __name__ == "__main__":
    unittest.main()
