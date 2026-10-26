"""Tests for the system policy: allowed destinations derived from the team context."""

import unittest

from purple_team.core.models import ActionItem, CeremonyOutput, Destination
from purple_team.policy import BlockReason, SystemPolicy
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
        policy = SystemPolicy.from_team_context(real_team_context(), 1500)
        self.assertEqual(policy.jira_project_key, "AGI")
        users = {"@ana.perez", "@bruno.diaz", "@carla.gomez", "@elena.ruiz"}
        self.assertEqual(policy.allowed_slack_users, frozenset(users))
        self.assertEqual(policy.allowed_slack_channels, frozenset({"#equipo-producto"}))
        self.assertEqual(policy.allowed_invitees, frozenset(MEMBER_EMAILS))
        self.assertEqual(policy.max_content_chars, 1500)

    def test_record_names_its_source_and_every_allowed_destination(self) -> None:
        record = default_policy().to_record()
        expected = {
            "name": "política del sistema",
            "always_on": True,
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


def item(destination: Destination, target: str, content: str = "Contenido.") -> ActionItem:
    return ActionItem(destination=destination, target=target, title="Título", content=content)


def event(*invitees: str, content: str = "Descripción.") -> ActionItem:
    return ActionItem(Destination.CALENDAR_EVENT, None, "Reunión", content, invitees)


class ScreenTest(unittest.TestCase):
    """The former output guard (handoff/24 section 1.2): now ``SystemPolicy.screen``."""

    def setUp(self) -> None:
        self.policy = default_policy(50)

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
        screening = self.policy.screen(CeremonyOutput(summary="R.", action_items=tuple(allowed)))
        self.assertEqual(screening.blocked, ())
        self.assertEqual(screening.output.action_items, tuple(allowed))

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
                output = CeremonyOutput(summary="R.", action_items=(action,))
                screening = self.policy.screen(output)
                self.assertEqual(screening.output.action_items, ())
                self.assertIs(screening.blocked[0].reason, reason)

    def test_destination_rule_wins_over_content_size(self) -> None:
        action = item(Destination.SLACK_MESSAGE, "@partner-review", "x" * 51)
        self.assertIs(self.policy.block_reason(action), BlockReason.SLACK_USER_NOT_ALLOWED)

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
        screening = self.policy.screen(output)
        blocked = screening.blocked
        self.assertEqual(screening.output.summary, "Resumen sin cambios.")
        self.assertEqual(len(screening.output.action_items), 2)
        self.assertEqual([block.index for block in blocked], [1, 3])
        self.assertEqual(blocked[0].item.target, "@partner-review")
        self.assertEqual(blocked[0].to_dict()["reason"], "slack_user_not_allowed")
        self.assertEqual(blocked[1].to_dict()["reason"], "calendar_invitee_not_allowed")
        self.assertEqual(
            blocked[1].to_dict()["item"],
            {
                "destination": "calendar_event",
                "title": "Reunión",
                "invitees": ["ana.perez@example.com", "auditoria@example.org"],
                "content": "Descripción.",
            },
        )
        data = screening.to_dict()
        self.assertEqual(list(data), ["applied", "blocked"])
        self.assertIs(data["applied"], True)


if __name__ == "__main__":
    unittest.main()
