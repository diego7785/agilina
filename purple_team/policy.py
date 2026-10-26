"""System policy: the single definition of "allowed destination", from the team context.

It is part of Agilina's design (the backend restricts every operation to the configured
project, board, channel and members), so it applies in every defense mode, also ``off``:
the pipeline drops the action items it does not allow before the tools run, and
``cases.validate_against_policy`` uses the very same predicate to check that every expected
item is reachable, so both can never diverge. It never inspects the summary.

Cycle 4 (handoff/18 section 2.3): ``jira_comment`` only on issues of the team project,
``slack_message`` only to members or to the team channel and ``calendar_event`` only when
every invitee is a member. Agilina holds Slack's ``chat:write.public`` scope (it can post in
any public channel without being invited), so this policy is the only control over channels.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Self

from purple_team.core.models import (
    SLACK_CHANNEL_PREFIX,
    ActionItem,
    CeremonyOutput,
    Destination,
    canonical_email,
    canonical_target,
)
from purple_team.team_context import ISSUE_NUMBER_PATTERN, TeamContext

POLICY_SOURCE: Final = "team_context"
POLICY_NAME: Final = "política del sistema"
ISSUE_KEY_SEPARATOR: Final = "-"


class BlockReason(StrEnum):
    """Why the system policy blocked an action item."""

    JIRA_ISSUE_NOT_ALLOWED = "jira_issue_not_allowed"
    SLACK_CHANNEL_NOT_ALLOWED = "slack_channel_not_allowed"
    SLACK_USER_NOT_ALLOWED = "slack_user_not_allowed"
    CALENDAR_INVITEE_NOT_ALLOWED = "calendar_invitee_not_allowed"
    CONTENT_TOO_LONG = "content_too_long"


@dataclass(frozen=True, slots=True)
class BlockedAction:
    """Action item of the model output that was not executed."""

    index: int
    item: ActionItem
    reason: BlockReason

    def to_dict(self) -> dict[str, object]:
        """JSON view."""
        return {"index": self.index, "reason": self.reason.value, "item": self.item.to_dict()}


@dataclass(frozen=True, slots=True)
class PolicyScreening:
    """Output of the system policy: what gets executed and what was blocked."""

    output: CeremonyOutput
    blocked: tuple[BlockedAction, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON view of the policy decision."""
        return {"applied": True, "blocked": [block.to_dict() for block in self.blocked]}


@dataclass(frozen=True, slots=True)
class SystemPolicy:
    """Allowed destinations (team project, members, team channel) and content size.

    Slack users and channels and the invitees are stored in their canonical form
    (``core.models``): ``"Ana.Perez"`` and ``"@ana.perez"`` are the same user.
    """

    jira_project_key: str
    allowed_slack_users: frozenset[str]
    allowed_slack_channels: frozenset[str]
    allowed_invitees: frozenset[str]
    max_content_chars: int

    @classmethod
    def from_team_context(cls, context: TeamContext, max_content_chars: int) -> Self:
        """Derive the policy from the team context (the only source of destinations)."""
        slack = Destination.SLACK_MESSAGE
        users = frozenset(canonical_target(slack, user) for user in context.member_slack_users)
        channel = canonical_target(slack, context.slack_channel)
        return cls(
            jira_project_key=context.jira_project_key,
            allowed_slack_users=users,
            allowed_slack_channels=frozenset({channel}),
            allowed_invitees=frozenset(canonical_email(email) for email in context.member_emails),
            max_content_chars=max_content_chars,
        )

    @property
    def jira_issue_pattern(self) -> str:
        """Recorded pattern of the allowed keys, with the project key as written (uppercase)."""
        return f"^{self.jira_project_key}{ISSUE_KEY_SEPARATOR}{ISSUE_NUMBER_PATTERN}$"

    def jira_issue_allowed(self, key: str) -> bool:
        """Any ``<PROJECT>-<n>`` (n >= 1) of the team project, listed in the context or not.

        The comparison uses the canonical key (no whitespace, casefolded) against the pattern
        with a casefolded project key, so ``agi-231`` and ``AGI-231`` are the same issue while
        ``AGI 231`` (no hyphen: ``agi231``) and ``OPS-12`` are not allowed.
        """
        project = re.escape(self.jira_project_key.casefold())
        pattern = f"^{project}{ISSUE_KEY_SEPARATOR}{ISSUE_NUMBER_PATTERN}$"
        return re.fullmatch(pattern, canonical_target(Destination.JIRA_COMMENT, key)) is not None

    def target_block_reason(self, destination: Destination, target: str) -> BlockReason | None:
        """Reason to block ``target`` (jira_comment or slack_message), or ``None``.

        A calendar event has no target: asking for it is an internal error (``ValueError``).
        """
        match destination:
            case Destination.JIRA_COMMENT:
                if self.jira_issue_allowed(target):
                    return None
                return BlockReason.JIRA_ISSUE_NOT_ALLOWED
            case Destination.SLACK_MESSAGE:
                canonical = canonical_target(destination, target)
                if canonical.startswith(SLACK_CHANNEL_PREFIX):
                    if canonical in self.allowed_slack_channels:
                        return None
                    return BlockReason.SLACK_CHANNEL_NOT_ALLOWED
                if canonical in self.allowed_slack_users:
                    return None
                return BlockReason.SLACK_USER_NOT_ALLOWED
            case Destination.CALENDAR_EVENT:
                raise ValueError("calendar_event no tiene target: usa invitee_block_reason")

    def invitee_block_reason(self, invitee: str) -> BlockReason | None:
        """``None`` when the invitee is the email of a member, otherwise the reason."""
        if canonical_email(invitee) in self.allowed_invitees:
            return None
        return BlockReason.CALENDAR_INVITEE_NOT_ALLOWED

    def block_reason(self, item: ActionItem) -> BlockReason | None:
        """First applicable reason (destination, then content size) or ``None``.

        A calendar event is blocked as a whole when any invitee is not a member (the first
        one in list order gives the reason): executing a different action from the one the
        model proposed would hide what happened.
        """
        reason = self._destination_reason(item)
        if reason is not None:
            return reason
        if len(item.content) > self.max_content_chars:
            return BlockReason.CONTENT_TOO_LONG
        return None

    def screen(self, output: CeremonyOutput) -> PolicyScreening:
        """Keep the allowed action items, in order, and the summary unchanged."""
        allowed: list[ActionItem] = []
        blocked: list[BlockedAction] = []
        for index, item in enumerate(output.action_items):
            reason = self.block_reason(item)
            if reason is None:
                allowed.append(item)
            else:
                blocked.append(BlockedAction(index=index, item=item, reason=reason))
        screened = CeremonyOutput(summary=output.summary, action_items=tuple(allowed))
        return PolicyScreening(output=screened, blocked=tuple(blocked))

    def _destination_reason(self, item: ActionItem) -> BlockReason | None:
        if item.destination is Destination.CALENDAR_EVENT:
            reasons = (self.invitee_block_reason(invitee) for invitee in item.invitees)
            return next((reason for reason in reasons if reason is not None), None)
        if item.target is None:
            raise ValueError(f"{item.destination.value} sin target")
        return self.target_block_reason(item.destination, item.target)

    def to_record(self) -> dict[str, object]:
        """System policy for the run records (always on, in every mode).

        ``jira_issue_pattern`` shows the project key in uppercase, as written in the context;
        the comparison is made on the canonical (casefolded, no whitespace) key.
        """
        return {
            "name": POLICY_NAME,
            "always_on": True,
            "source": POLICY_SOURCE,
            "jira_project_key": self.jira_project_key,
            "jira_issue_pattern": self.jira_issue_pattern,
            "allowed_slack_users": sorted(self.allowed_slack_users),
            "allowed_slack_channels": sorted(self.allowed_slack_channels),
            "allowed_calendar_invitees": sorted(self.allowed_invitees),
            "max_content_chars": self.max_content_chars,
        }
