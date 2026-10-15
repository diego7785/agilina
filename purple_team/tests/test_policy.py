"""Tests for the single "allowed destination" predicate derived from the team context."""

import unittest

from purple_team.core.models import ActionItem, Destination
from purple_team.policy import BlockReason, DefensePolicy
from purple_team.tests.support import default_policy, real_team_context

MEMBER_EMAILS = (
    "ana.perez@example.com",
    "bruno.diaz@example.com",
    "carla.gomez@example.com",
    "elena.ruiz@example.com",
)

ALLOWED_SLACK_TARGETS = (
    "@ana.perez",
    "ana.perez",
    " @Ana.Perez ",
    "#equipo-producto",
    "#Equipo-Producto",
)
EXTERNAL_SLACK_USERS = ("@partner-review", "Ana Pérez", "ana.perez@example.com", "equipo-producto")
EXTERNAL_INVITEES = ("auditoria@example.org", "soporte@example.com", "Carla Gómez", "@carla.gomez")


def calendar(*invitees: str, content: str = "Reunión.") -> ActionItem:
    return ActionItem(Destination.CALENDAR_EVENT, None, "Reunión", content, invitees)


class FromTeamContextTest(unittest.TestCase):
    def test_policy_comes_from_the_team_context(self) -> None:
        policy = DefensePolicy.from_team_context(real_team_context(), 1500)
        self.assertEqual(policy.jira_project_key, "AGI")
        users = {"@ana.perez", "@bruno.diaz", "@carla.gomez", "@elena.ruiz"}
        self.assertEqual(policy.allowed_slack_users, frozenset(users))
        self.assertEqual(policy.allowed_slack_channels, frozenset({"#equipo-producto"}))
        self.assertEqual(policy.allowed_invitees, frozenset(MEMBER_EMAILS))
        self.assertEqual(policy.max_content_chars, 1500)

    def test_record_names_its_source_and_every_allowed_destination(self) -> None:
        record = default_policy().to_record()
        expected = {
            "source": "team_context",
            "jira_project_key": "AGI",
            "jira_issue_pattern": "^AGI-[1-9][0-9]*$",
            "allowed_slack_users": ["@ana.perez", "@bruno.diaz", "@carla.gomez", "@elena.ruiz"],
            "allowed_slack_channels": ["#equipo-producto"],
            "allowed_calendar_invitees": list(MEMBER_EMAILS),
            "max_content_chars": 1500,
        }
        self.assertEqual(record, expected)


class TargetBlockReasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = default_policy(10)

    def test_jira_allows_any_issue_of_the_team_project(self) -> None:
        reason = self.policy.target_block_reason
        for key in ("AGI-231", "agi-231", " AGI-231 ", "A GI-231", "AGI-999"):
            with self.subTest(key=key):
                self.assertIsNone(reason(Destination.JIRA_COMMENT, key))
        for key in ("OPS-12", "AGI", "AGI 231", "AGI-0", "AGI-012", "AGI-231-1", "XAGI-231"):
            with self.subTest(key=key):
                self.assertIs(
                    reason(Destination.JIRA_COMMENT, key),
                    BlockReason.JIRA_ISSUE_NOT_ALLOWED,
                )

    def test_slack_allows_members_and_the_team_channel_only(self) -> None:
        reason = self.policy.target_block_reason
        for target in ALLOWED_SLACK_TARGETS:
            with self.subTest(target=target):
                self.assertIsNone(reason(Destination.SLACK_MESSAGE, target))
        for target in ("#general", "#soporte-urgente", "#equipo-producto-ext"):
            with self.subTest(target=target):
                self.assertIs(
                    reason(Destination.SLACK_MESSAGE, target),
                    BlockReason.SLACK_CHANNEL_NOT_ALLOWED,
                )
        for target in EXTERNAL_SLACK_USERS:
            with self.subTest(target=target):
                self.assertIs(
                    reason(Destination.SLACK_MESSAGE, target),
                    BlockReason.SLACK_USER_NOT_ALLOWED,
                )

    def test_calendar_has_no_target(self) -> None:
        with self.assertRaises(ValueError):
            self.policy.target_block_reason(Destination.CALENDAR_EVENT, "x")

    def test_invitees_must_be_member_emails(self) -> None:
        self.assertIsNone(self.policy.invitee_block_reason(" Carla.Gomez@Example.com "))
        for invitee in EXTERNAL_INVITEES:
            with self.subTest(invitee=invitee):
                self.assertIs(
                    self.policy.invitee_block_reason(invitee),
                    BlockReason.CALENDAR_INVITEE_NOT_ALLOWED,
                )


class BlockReasonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = default_policy(10)

    def test_checks_destination_then_content_size(self) -> None:
        allowed = ActionItem(Destination.JIRA_COMMENT, "AGI-231", "T", "corto")
        too_long = ActionItem(Destination.JIRA_COMMENT, "AGI-231", "T", "x" * 11)
        both = ActionItem(Destination.JIRA_COMMENT, "OPS-12", "T", "x" * 11)
        self.assertIsNone(self.policy.block_reason(allowed))
        self.assertIs(self.policy.block_reason(too_long), BlockReason.CONTENT_TOO_LONG)
        self.assertIs(self.policy.block_reason(both), BlockReason.JIRA_ISSUE_NOT_ALLOWED)

    def test_one_external_invitee_blocks_the_whole_event(self) -> None:
        self.assertIsNone(self.policy.block_reason(calendar(*MEMBER_EMAILS)))
        mixed = calendar("ana.perez@example.com", "auditoria@example.org")
        self.assertIs(self.policy.block_reason(mixed), BlockReason.CALENDAR_INVITEE_NOT_ALLOWED)
        external_and_long = calendar("auditoria@example.org", content="x" * 11)
        self.assertIs(
            self.policy.block_reason(external_and_long),
            BlockReason.CALENDAR_INVITEE_NOT_ALLOWED,
        )
        long_event = calendar("ana.perez@example.com", content="x" * 11)
        self.assertIs(self.policy.block_reason(long_event), BlockReason.CONTENT_TOO_LONG)

    def test_slack_reasons_come_before_content_size(self) -> None:
        channel = ActionItem(Destination.SLACK_MESSAGE, "#general", "T", "x" * 11)
        user = ActionItem(Destination.SLACK_MESSAGE, "@partner-review", "T", "corto")
        self.assertIs(self.policy.block_reason(channel), BlockReason.SLACK_CHANNEL_NOT_ALLOWED)
        self.assertIs(self.policy.block_reason(user), BlockReason.SLACK_USER_NOT_ALLOWED)


if __name__ == "__main__":
    unittest.main()
