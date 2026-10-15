"""Simulated Jira (comments), calendar and Slack tools: the actions the model may propose.

They open no network connection, write no files and start no processes: they only return
the record of the call the model requested and log it. Agilina never creates Jira issues or
sends emails (email is only used for access invitations, out of the harness scope).
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Final

from purple_team.core.models import (
    SLACK_CHANNEL_PREFIX,
    ActionItem,
    Destination,
    canonical_target,
)
from purple_team.tools.base import SIMULATED_STATUS, ActionTool, ToolArgument, ToolCallRecord

JIRA_COMMENT_OPERATION: Final = "add_comment"
CALENDAR_OPERATION: Final = "create_event"
SLACK_OPERATION: Final = "post_message"
SLACK_CHANNEL_TYPE: Final = "channel"
SLACK_USER_TYPE: Final = "user"

_LOGGER = logging.getLogger(__name__)


def _simulate(
    sequence: int,
    destination: Destination,
    operation: str,
    arguments: Mapping[str, ToolArgument],
) -> ToolCallRecord:
    _LOGGER.info("SIMULATED %s %s", operation, dict(arguments))
    return ToolCallRecord(
        sequence=sequence,
        tool=destination.value,
        operation=operation,
        arguments=dict(arguments),
        status=SIMULATED_STATUS,
    )


def _required_target(item: ActionItem) -> str:
    if item.target is None:
        raise ValueError(f"{item.destination.value} sin target")
    return item.target


class SimulatedJiraComment:
    """Records an ``add_comment`` call on an existing issue."""

    @property
    def destination(self) -> Destination:
        """Jira comment."""
        return Destination.JIRA_COMMENT

    def execute(self, item: ActionItem, sequence: int) -> ToolCallRecord:
        """Record the comment the model asked to add."""
        arguments: dict[str, ToolArgument] = {
            "issue_key": _required_target(item),
            "title": item.title,
            "comment": item.content,
        }
        return _simulate(sequence, self.destination, JIRA_COMMENT_OPERATION, arguments)


class SimulatedCalendar:
    """Records a ``create_event`` call with its invitees."""

    @property
    def destination(self) -> Destination:
        """Calendar event."""
        return Destination.CALENDAR_EVENT

    def execute(self, item: ActionItem, sequence: int) -> ToolCallRecord:
        """Record the meeting the model asked to schedule."""
        arguments: dict[str, ToolArgument] = {
            "title": item.title,
            "invitees": item.invitees,
            "description": item.content,
        }
        return _simulate(sequence, self.destination, CALENDAR_OPERATION, arguments)


class SimulatedSlack:
    """Records a ``post_message`` call to a user or a channel."""

    @property
    def destination(self) -> Destination:
        """Slack message."""
        return Destination.SLACK_MESSAGE

    def execute(self, item: ActionItem, sequence: int) -> ToolCallRecord:
        """Record the message the model asked to post."""
        target = _required_target(item)
        is_channel = canonical_target(self.destination, target).startswith(SLACK_CHANNEL_PREFIX)
        arguments: dict[str, ToolArgument] = {
            "conversation": target,
            "conversation_type": SLACK_CHANNEL_TYPE if is_channel else SLACK_USER_TYPE,
            "title": item.title,
            "text": item.content,
        }
        return _simulate(sequence, self.destination, SLACK_OPERATION, arguments)


class ToolDispatcher:
    """Routes every action item to the tool of its destination, in order."""

    def __init__(self, tools: Sequence[ActionTool]) -> None:
        self._tools: dict[Destination, ActionTool] = {}
        for tool in tools:
            if tool.destination in self._tools:
                raise ValueError(f"Herramienta duplicada para {tool.destination.value}")
            self._tools[tool.destination] = tool

    def dispatch(self, items: Sequence[ActionItem]) -> tuple[ToolCallRecord, ...]:
        """Execute the items with sequence numbers starting at 1."""
        records = []
        for sequence, item in enumerate(items, start=1):
            tool = self._tools.get(item.destination)
            if tool is None:
                raise LookupError(f"No hay herramienta para {item.destination.value}")
            records.append(tool.execute(item, sequence))
        return tuple(records)
