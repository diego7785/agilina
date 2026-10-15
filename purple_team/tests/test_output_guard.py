"""Tests for the output guard: destinations derived from the team context."""

import unittest

from purple_team.core.models import ActionItem, CeremonyOutput, Destination
from purple_team.defense.output_guard import OutputGuard
from purple_team.policy import BlockReason
from purple_team.tests.support import default_policy

MAX_CONTENT_CHARS = 50


def item(destination: Destination, target: str, content: str = "Contenido.") -> ActionItem:
    return ActionItem(destination=destination, target=target, title="Título", content=content)


def event(*invitees: str, content: str = "Descripción.") -> ActionItem:
    return ActionItem(Destination.CALENDAR_EVENT, None, "Reunión", content, invitees)


class OutputGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = OutputGuard(default_policy(MAX_CONTENT_CHARS))

    def test_allows_items_that_follow_the_policy(self) -> None:
        allowed = [
            item(Destination.JIRA_COMMENT, "AGI-231"),
            item(Destination.JIRA_COMMENT, " agi-198 "),
            item(Destination.JIRA_COMMENT, "AGI-9999"),
            item(Destination.SLACK_MESSAGE, "@ana.perez"),
            item(Destination.SLACK_MESSAGE, "Elena.Ruiz"),
            item(Destination.SLACK_MESSAGE, "#equipo-producto"),
            event("ana.perez@example.com", " Carla.Gomez@EXAMPLE.COM "),
        ]
        for action in allowed:
            with self.subTest(item=action):
                self.assertIsNone(self.guard.reason_to_block(action))

    def test_blocks_items_outside_the_policy(self) -> None:
        cases = [
            (item(Destination.JIRA_COMMENT, "OPS-12"), BlockReason.JIRA_ISSUE_NOT_ALLOWED),
            (item(Destination.JIRA_COMMENT, "AGI"), BlockReason.JIRA_ISSUE_NOT_ALLOWED),
            (item(Destination.SLACK_MESSAGE, "#general"), BlockReason.SLACK_CHANNEL_NOT_ALLOWED),
            (
                item(Destination.SLACK_MESSAGE, "#soporte-urgente"),
                BlockReason.SLACK_CHANNEL_NOT_ALLOWED,
            ),
            (
                item(Destination.SLACK_MESSAGE, "@partner-review"),
                BlockReason.SLACK_USER_NOT_ALLOWED,
            ),
            (item(Destination.SLACK_MESSAGE, "Ana Pérez"), BlockReason.SLACK_USER_NOT_ALLOWED),
            (event("auditoria@example.org"), BlockReason.CALENDAR_INVITEE_NOT_ALLOWED),
            (
                event("ana.perez@example.com", "auditoria@example.org"),
                BlockReason.CALENDAR_INVITEE_NOT_ALLOWED,
            ),
            (
                item(Destination.JIRA_COMMENT, "AGI-231", "x" * 51),
                BlockReason.CONTENT_TOO_LONG,
            ),
        ]
        for action, reason in cases:
            with self.subTest(item=action, reason=reason):
                self.assertIs(self.guard.reason_to_block(action), reason)

    def test_destination_rule_wins_over_content_size(self) -> None:
        action = item(Destination.SLACK_MESSAGE, "@partner-review", "x" * 51)
        self.assertIs(self.guard.reason_to_block(action), BlockReason.SLACK_USER_NOT_ALLOWED)

    def test_screen_keeps_summary_and_reports_blocked_indexes(self) -> None:
        output = CeremonyOutput(
            summary="Resumen sin cambios.",
            action_items=(
                item(Destination.JIRA_COMMENT, "AGI-214"),
                item(Destination.SLACK_MESSAGE, "@partner-review"),
                item(Destination.SLACK_MESSAGE, "#equipo-producto"),
                event("ana.perez@example.com", "auditoria@example.org"),
            ),
        )
        screened, blocked = self.guard.screen(output)
        self.assertEqual(screened.summary, "Resumen sin cambios.")
        self.assertEqual(len(screened.action_items), 2)
        self.assertEqual([block.index for block in blocked], [1, 3])
        self.assertEqual(blocked[0].item.target, "@partner-review")
        self.assertEqual(blocked[0].to_dict()["reason"], "slack_user_not_allowed")
        self.assertEqual(blocked[1].to_dict()["reason"], "calendar_invitee_not_allowed")
        blocked_item = blocked[1].to_dict()["item"]
        self.assertEqual(
            blocked_item,
            {
                "destination": "calendar_event",
                "title": "Reunión",
                "invitees": ["ana.perez@example.com", "auditoria@example.org"],
                "content": "Descripción.",
            },
        )


if __name__ == "__main__":
    unittest.main()
