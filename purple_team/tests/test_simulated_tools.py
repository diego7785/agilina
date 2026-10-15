"""Tests for the simulated tools: they only record the requested call."""

import unittest

from purple_team.core.models import ActionItem, Destination
from purple_team.tools.base import SIMULATED_STATUS, ActionTool
from purple_team.tools.simulated import (
    SimulatedCalendar,
    SimulatedJiraComment,
    SimulatedSlack,
    ToolDispatcher,
)

JIRA_ITEM = ActionItem(
    Destination.JIRA_COMMENT,
    "AGI-198",
    "Error de paginación",
    "Error de paginación en la exportación.",
)
CALENDAR_ITEM = ActionItem(
    Destination.CALENDAR_EVENT,
    None,
    "Refinamiento",
    "Refinamiento del backlog.",
    ("ana.perez@example.com", "bruno.diaz@example.com"),
)
SLACK_USER_ITEM = ActionItem(Destination.SLACK_MESSAGE, "@ana.perez", "Estado", "Pruebas al día.")
SLACK_CHANNEL_ITEM = ActionItem(Destination.SLACK_MESSAGE, "#equipo-producto", "Demo", "Demo.")


def all_tools() -> ToolDispatcher:
    return ToolDispatcher([SimulatedJiraComment(), SimulatedCalendar(), SimulatedSlack()])


class SimulatedToolsTest(unittest.TestCase):
    def test_tools_satisfy_the_port(self) -> None:
        for tool in (SimulatedJiraComment(), SimulatedCalendar(), SimulatedSlack()):
            with self.subTest(tool=type(tool).__name__):
                self.assertIsInstance(tool, ActionTool)

    def test_records_each_call_in_order_with_its_arguments(self) -> None:
        records = all_tools().dispatch([JIRA_ITEM, CALENDAR_ITEM, SLACK_USER_ITEM])
        self.assertEqual([record.sequence for record in records], [1, 2, 3])
        self.assertEqual(
            [(record.tool, record.operation) for record in records],
            [
                ("jira_comment", "add_comment"),
                ("calendar_event", "create_event"),
                ("slack_message", "post_message"),
            ],
        )
        self.assertEqual(
            records[0].arguments,
            {
                "issue_key": "AGI-198",
                "title": "Error de paginación",
                "comment": "Error de paginación en la exportación.",
            },
        )
        self.assertEqual(
            records[1].to_dict(),
            {
                "sequence": 2,
                "origin": "model",
                "tool": "calendar_event",
                "operation": "create_event",
                "arguments": {
                    "title": "Refinamiento",
                    "invitees": ["ana.perez@example.com", "bruno.diaz@example.com"],
                    "description": "Refinamiento del backlog.",
                },
                "status": SIMULATED_STATUS,
            },
        )

    def test_slack_records_whether_it_writes_to_a_user_or_a_channel(self) -> None:
        user, channel = all_tools().dispatch([SLACK_USER_ITEM, SLACK_CHANNEL_ITEM])
        self.assertEqual(
            user.arguments,
            {
                "conversation": "@ana.perez",
                "conversation_type": "user",
                "title": "Estado",
                "text": "Pruebas al día.",
            },
        )
        self.assertEqual(channel.arguments["conversation_type"], "channel")
        bare = ActionItem(Destination.SLACK_MESSAGE, "Ana.Perez", "Estado", "Hola.")
        self.assertEqual(SimulatedSlack().execute(bare, 1).arguments["conversation_type"], "user")
        self.assertEqual(SimulatedSlack().execute(bare, 1).arguments["conversation"], "Ana.Perez")

    def test_every_call_is_marked_as_simulated_and_comes_from_the_model(self) -> None:
        records = all_tools().dispatch([JIRA_ITEM, CALENDAR_ITEM, SLACK_CHANNEL_ITEM])
        self.assertTrue(all(record.status == SIMULATED_STATUS for record in records))
        self.assertTrue(all(record.to_dict()["origin"] == "model" for record in records))

    def test_no_items_means_no_calls(self) -> None:
        self.assertEqual(all_tools().dispatch([]), ())

    def test_missing_tool_is_reported(self) -> None:
        with self.assertRaises(LookupError):
            ToolDispatcher([SimulatedJiraComment()]).dispatch([SLACK_USER_ITEM])

    def test_duplicate_tools_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ToolDispatcher([SimulatedSlack(), SimulatedSlack()])


if __name__ == "__main__":
    unittest.main()
