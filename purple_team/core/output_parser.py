"""Parser and validator of the JSON closing returned by the model.

Every action item needs ``destination``, ``title`` and ``content``. ``jira_comment`` and
``slack_message`` also need ``target`` (``invitees`` is ignored); ``calendar_event`` needs a
non-empty ``invitees`` list (``target`` is ignored). Texts are kept as written: canonical forms
(``core.models.canonical_target``) are only used to compare.
"""

import json
import re
from collections.abc import Mapping
from typing import Final

from purple_team.core.models import ActionItem, CeremonyOutput, Destination

# A Markdown code fence wrapping the whole answer (```json ... ``` or ``` ... ```).
_CODE_FENCE: Final = re.compile(
    r"\A\s*```[A-Za-z]*[ \t]*\n(?P<body>.*?)\n?[ \t]*```\s*\Z",
    re.DOTALL,
)
# Reasoning blocks that models with a thinking mode may write inline before the answer.
_THINK_BLOCK: Final = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
TEXT_FIELDS: Final = ("title", "content")
TARGET_FIELD: Final = "target"
INVITEES_FIELD: Final = "invitees"


class OutputFormatError(ValueError):
    """The model output is not a valid ceremony closing."""


def parse_ceremony_output(raw_text: str) -> CeremonyOutput:
    """Validate the raw model text and build a ``CeremonyOutput``.

    Closed ``<think>...</think>`` blocks and a code fence wrapping the whole answer are
    removed first. Unknown keys are ignored because real models tend to add them; any other
    violation raises ``OutputFormatError`` naming the field and the reason.
    """
    try:
        data = json.loads(_strip_code_fence(_strip_think_blocks(raw_text)))
    except json.JSONDecodeError as exc:
        message = f"la salida no es JSON válido: {exc.msg} (línea {exc.lineno})"
        raise OutputFormatError(message) from exc
    if not isinstance(data, dict):
        raise OutputFormatError("la salida debe ser un objeto JSON")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise OutputFormatError("el campo summary debe ser un texto no vacío")
    raw_items = data.get("action_items")
    if not isinstance(raw_items, list):
        raise OutputFormatError("el campo action_items debe ser una lista")
    items = tuple(_parse_item(index, item) for index, item in enumerate(raw_items))
    return CeremonyOutput(summary=summary, action_items=items)


def _strip_think_blocks(raw_text: str) -> str:
    return _THINK_BLOCK.sub("", raw_text)


def _strip_code_fence(raw_text: str) -> str:
    match = _CODE_FENCE.match(raw_text)
    return match.group("body") if match else raw_text


def _parse_item(index: int, data: object) -> ActionItem:
    if not isinstance(data, dict):
        raise OutputFormatError(f"action_items[{index}] debe ser un objeto")
    destination = data.get("destination")
    valid = ", ".join(member.value for member in Destination)
    if not isinstance(destination, str) or destination not in set(Destination):
        message = f"action_items[{index}].destination debe ser uno de: {valid}"
        raise OutputFormatError(message)
    kind = Destination(destination)
    texts = {field_name: _text(data, index, field_name) for field_name in TEXT_FIELDS}
    if kind is Destination.CALENDAR_EVENT:
        return ActionItem(
            destination=kind,
            target=None,
            title=texts["title"],
            content=texts["content"],
            invitees=_invitees(data, index),
        )
    return ActionItem(
        destination=kind,
        target=_target(data, index),
        title=texts["title"],
        content=texts["content"],
    )


def _text(data: Mapping[str, object], index: int, field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        message = f"action_items[{index}].{field_name} debe ser un texto no vacío"
        raise OutputFormatError(message)
    return value


def _target(data: Mapping[str, object], index: int) -> str:
    """Issue key or Slack user/channel, kept as written (canonical forms only compare)."""
    return _text(data, index, TARGET_FIELD)


def _invitees(data: Mapping[str, object], index: int) -> tuple[str, ...]:
    """Non-empty list of non-empty texts; duplicates are kept (the policy checks each one)."""
    value = data.get(INVITEES_FIELD)
    if not isinstance(value, list) or not value or not all(_is_text(item) for item in value):
        message = f"action_items[{index}].{INVITEES_FIELD} debe ser una lista no vacía de textos"
        raise OutputFormatError(message)
    return tuple(value)


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
