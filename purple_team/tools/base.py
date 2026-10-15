"""Port of the action tools and the records of what the harness "executed".

Two kinds of record are kept apart: ``ToolCallRecord`` is an action the model proposed
(``origin = "model"``) and ``SystemOutputRecord`` is an automatic output of the system whose
destination comes from the team configuration (``origin = "system"``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from purple_team.core.models import ActionItem, Destination

SIMULATED_STATUS: Final = "simulated"
MODEL_ORIGIN: Final = "model"
SYSTEM_ORIGIN: Final = "system"

type ToolArgument = str | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """What the model asked a tool to do; nothing was actually executed."""

    sequence: int
    tool: str
    operation: str
    arguments: Mapping[str, ToolArgument]
    status: str

    def to_dict(self) -> dict[str, object]:
        """JSON view of the call (tuples as lists)."""
        return {
            "sequence": self.sequence,
            "origin": MODEL_ORIGIN,
            "tool": self.tool,
            "operation": self.operation,
            "arguments": {
                name: list(value) if isinstance(value, tuple) else value
                for name, value in self.arguments.items()
            },
            "status": self.status,
        }


class SystemChannel(StrEnum):
    """Automatic outputs Agilina always produces, without approval."""

    ONEDRIVE_EXCEL = "onedrive_excel"
    SLACK_DM = "slack_dm"


@dataclass(frozen=True, slots=True)
class SystemOutputRecord:
    """Automatic output of the system; ``destination`` is fixed by the configuration.

    ``configured_by`` names the configuration key the destination comes from, so a record
    shows that the model never chose it.
    """

    sequence: int
    channel: SystemChannel
    operation: str
    destination: str
    configured_by: str
    payload: Mapping[str, object]
    status: str

    def to_dict(self) -> dict[str, object]:
        """JSON view of the output."""
        return {
            "sequence": self.sequence,
            "origin": SYSTEM_ORIGIN,
            "channel": self.channel.value,
            "operation": self.operation,
            "destination": self.destination,
            "configured_by": self.configured_by,
            "payload": dict(self.payload),
            "status": self.status,
        }


@runtime_checkable
class ActionTool(Protocol):
    """Tool that executes the action items of one destination."""

    @property
    def destination(self) -> Destination:
        """Destination handled by the tool."""

    def execute(self, item: ActionItem, sequence: int) -> ToolCallRecord:
        """Execute (or simulate) the action item and return the record."""
