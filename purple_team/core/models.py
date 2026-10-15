"""Structured output of the ceremony closing: summary and action items.

Cycle 4 (handoff/18): the action items are the third-party actions Agilina really proposes
(comment an existing Jira issue, schedule a calendar event, post a Slack message). The Excel
in OneDrive and the direct messages with the summary are automatic system outputs whose
destinations come from the team configuration (``tools/system_outputs.py``), never from the
model, so they are not action items.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Destination(StrEnum):
    """Third-party action that Agilina may propose (cycle 4: real action model)."""

    JIRA_COMMENT = "jira_comment"
    CALENDAR_EVENT = "calendar_event"
    SLACK_MESSAGE = "slack_message"


SLACK_CHANNEL_PREFIX: Final = "#"
SLACK_USER_PREFIX: Final = "@"


@dataclass(frozen=True, slots=True)
class ActionItem:
    """Action derived from the ceremony.

    ``target`` is the issue key (jira_comment) or the Slack user/channel (slack_message) and is
    ``None`` for calendar_event, whose recipients are ``invitees`` (emails). ``content`` is the
    comment, the event description or the message.
    """

    destination: Destination
    target: str | None
    title: str
    content: str
    invitees: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """JSON view with the keys of the item type (the same keys the model produces)."""
        if self.destination is Destination.CALENDAR_EVENT:
            return {
                "destination": self.destination.value,
                "title": self.title,
                "invitees": list(self.invitees),
                "content": self.content,
            }
        return {
            "destination": self.destination.value,
            "target": self.target,
            "title": self.title,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class CeremonyOutput:
    """Closing of the ceremony as returned by the model (or after the output guard)."""

    summary: str
    action_items: tuple[ActionItem, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON view with the same keys the model produces."""
        return {
            "summary": self.summary,
            "action_items": [item.to_dict() for item in self.action_items],
        }


def canonical_target(destination: Destination, target: str) -> str:
    """Single comparison form of a target, shared by the output policy and the matchers.

    jira_comment: no whitespace at all and casefolded ("AGI-231" -> "agi-231"). slack_message:
    stripped and casefolded, with ``@`` prepended when it is neither a channel (``#``) nor a
    user (``@``) ("ana.perez" -> "@ana.perez"). calendar_event has no target: asking for its
    canonical target is an internal error (``ValueError``).
    """
    match destination:
        case Destination.JIRA_COMMENT:
            return "".join(target.split()).casefold()
        case Destination.SLACK_MESSAGE:
            folded = target.strip().casefold()
            if folded.startswith((SLACK_CHANNEL_PREFIX, SLACK_USER_PREFIX)):
                return folded
            return f"{SLACK_USER_PREFIX}{folded}"
        case Destination.CALENDAR_EVENT:
            raise ValueError("calendar_event no tiene target")


def canonical_email(address: str) -> str:
    """Comparison form of an email address (stripped and casefolded)."""
    return address.strip().casefold()


def ceremony_output_json_schema() -> dict[str, object]:
    """JSON Schema of the closing that ``core.output_parser`` accepts (a fresh copy).

    It is flat and permissive on purpose (no ``oneOf``, which Ollama's grammar does not
    guarantee): every item may carry ``target`` and ``invitees`` and only ``destination``,
    ``title`` and ``content`` are required. The parser remains the only validator and asks for
    the fields that apply to each destination.
    """
    text = {"type": "string"}
    item = {
        "type": "object",
        "properties": {
            "destination": {"type": "string", "enum": [member.value for member in Destination]},
            "target": text,
            "title": text,
            "invitees": {"type": "array", "items": text},
            "content": text,
        },
        "required": ["destination", "title", "content"],
    }
    return {
        "type": "object",
        "properties": {
            "summary": text,
            "action_items": {"type": "array", "items": item},
        },
        "required": ["summary", "action_items"],
    }
