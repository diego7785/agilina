"""Tests for the validation of the model output."""

import json
import unittest

from purple_team.core.models import ActionItem, CeremonyOutput, Destination
from purple_team.core.output_parser import OutputFormatError, parse_ceremony_output

JIRA_ITEM = {
    "destination": "jira_comment",
    "target": "AGI-198",
    "title": "Error de paginación",
    "content": "Comentar el error de paginación.",
}
CALENDAR_ITEM = {
    "destination": "calendar_event",
    "title": "Refinamiento del jueves",
    "invitees": ["ana.perez@example.com", "bruno.diaz@example.com"],
    "content": "Refinamiento del backlog el jueves.",
}
SLACK_ITEM = {
    "destination": "slack_message",
    "target": "#equipo-producto",
    "title": "Demo del viernes",
    "content": "La demo del viernes sigue en pie.",
}
VALID_OUTPUT = {"summary": "Daily sin bloqueos.", "action_items": [JIRA_ITEM]}


def closing(*items: object) -> str:
    """JSON text of a closing with the given action items."""
    return json.dumps({"summary": "x", "action_items": list(items)})


class ThinkingModelOutputTest(unittest.TestCase):
    def test_think_block_before_the_json_is_ignored(self) -> None:
        raw = "<think>\nEl equipo acordó un ticket.\n</think>\n\n" + json.dumps(VALID_OUTPUT)
        self.assertEqual(parse_ceremony_output(raw).summary, "Daily sin bloqueos.")

    def test_think_block_and_json_fence_together(self) -> None:
        raw = "<think>pienso</think>\n```json\n" + json.dumps(VALID_OUTPUT) + "\n```\n"
        self.assertEqual(len(parse_ceremony_output(raw).action_items), 1)

    def test_unclosed_think_block_is_still_invalid(self) -> None:
        with self.assertRaises(OutputFormatError):
            parse_ceremony_output("<think>pienso " + json.dumps(VALID_OUTPUT))

    def test_prose_around_the_json_is_still_invalid(self) -> None:
        with self.assertRaises(OutputFormatError):
            parse_ceremony_output("Aquí tienes el cierre: " + json.dumps(VALID_OUTPUT))


class ParseCeremonyOutputTest(unittest.TestCase):
    def test_parses_one_valid_item_of_each_type(self) -> None:
        output = parse_ceremony_output(closing(JIRA_ITEM, CALENDAR_ITEM, SLACK_ITEM))
        expected = (
            ActionItem(
                destination=Destination.JIRA_COMMENT,
                target="AGI-198",
                title="Error de paginación",
                content="Comentar el error de paginación.",
            ),
            ActionItem(
                destination=Destination.CALENDAR_EVENT,
                target=None,
                title="Refinamiento del jueves",
                content="Refinamiento del backlog el jueves.",
                invitees=("ana.perez@example.com", "bruno.diaz@example.com"),
            ),
            ActionItem(
                destination=Destination.SLACK_MESSAGE,
                target="#equipo-producto",
                title="Demo del viernes",
                content="La demo del viernes sigue en pie.",
            ),
        )
        self.assertEqual(output, CeremonyOutput("x", expected))

    def test_item_views_keep_the_keys_of_each_type(self) -> None:
        output = parse_ceremony_output(closing(JIRA_ITEM, CALENDAR_ITEM, SLACK_ITEM))
        views = [item.to_dict() for item in output.action_items]
        self.assertEqual(views, [JIRA_ITEM, CALENDAR_ITEM, SLACK_ITEM])

    def test_calendar_ignores_target_and_others_ignore_invitees(self) -> None:
        calendar = {**CALENDAR_ITEM, "target": "#equipo-producto"}
        slack = {**SLACK_ITEM, "invitees": ["x@example.org"]}
        output = parse_ceremony_output(closing(calendar, slack))
        self.assertIsNone(output.action_items[0].target)
        self.assertEqual(output.action_items[1].invitees, ())

    def test_texts_are_kept_as_written(self) -> None:
        item = {**SLACK_ITEM, "target": " Ana.Perez "}
        repeated = ["Ana.Perez@Example.com", "Ana.Perez@Example.com"]
        calendar = {**CALENDAR_ITEM, "invitees": repeated}
        output = parse_ceremony_output(closing(item, calendar))
        self.assertEqual(output.action_items[0].target, " Ana.Perez ")
        self.assertEqual(len(output.action_items[1].invitees), 2)

    def test_strips_a_code_fence_around_the_whole_answer(self) -> None:
        fenced = "```json\n" + json.dumps(VALID_OUTPUT) + "\n```\n"
        self.assertEqual(len(parse_ceremony_output(fenced).action_items), 1)

    def test_ignores_unknown_keys(self) -> None:
        data = {**VALID_OUTPUT, "confidence": 0.9}
        self.assertEqual(parse_ceremony_output(json.dumps(data)).summary, "Daily sin bloqueos.")

    def test_accepts_an_empty_action_item_list(self) -> None:
        output = parse_ceremony_output('{"summary": "Nada que hacer.", "action_items": []}')
        self.assertEqual(output.action_items, ())

    def test_rejects_text_that_is_not_json(self) -> None:
        with self.assertRaises(OutputFormatError) as raised:
            parse_ceremony_output("Claro, aquí tienes el resumen.")
        self.assertIsInstance(raised.exception.__cause__, json.JSONDecodeError)

    def test_rejects_invalid_structures(self) -> None:
        invalid_outputs: list[object] = [
            [],
            {"action_items": []},
            {"summary": "  ", "action_items": []},
            {"summary": "x", "action_items": {}},
            {"summary": "x", "action_items": ["texto"]},
            {"summary": "x", "action_items": [{**JIRA_ITEM, "content": 3}]},
        ]
        for data in invalid_outputs:
            raw = json.dumps(data)
            with self.subTest(raw=raw):
                with self.assertRaises(OutputFormatError):
                    parse_ceremony_output(raw)

    def test_old_and_unknown_destinations_invalidate_the_output(self) -> None:
        for destination in ("jira", "email", "onedrive", "slack", "calendar"):
            raw = closing({**SLACK_ITEM, "destination": destination})
            with self.subTest(destination=destination):
                with self.assertRaises(OutputFormatError) as raised:
                    parse_ceremony_output(raw)
                self.assertIn("jira_comment, calendar_event, slack_message", str(raised.exception))

    def test_jira_and_slack_require_a_target(self) -> None:
        for item in (JIRA_ITEM, SLACK_ITEM):
            without_target = {key: value for key, value in item.items() if key != "target"}
            for broken in (without_target, {**item, "target": " "}):
                with self.subTest(item=broken):
                    with self.assertRaises(OutputFormatError) as raised:
                        parse_ceremony_output(closing(broken))
                    self.assertIn("action_items[0].target", str(raised.exception))

    def test_calendar_requires_a_non_empty_invitee_list(self) -> None:
        missing = {key: value for key, value in CALENDAR_ITEM.items() if key != "invitees"}
        broken_items = (
            missing,
            {**CALENDAR_ITEM, "invitees": []},
            {**CALENDAR_ITEM, "invitees": "ana.perez@example.com"},
            {**CALENDAR_ITEM, "invitees": ["ana.perez@example.com", ""]},
            {**CALENDAR_ITEM, "invitees": [3]},
        )
        for broken in broken_items:
            with self.subTest(item=broken):
                with self.assertRaises(OutputFormatError) as raised:
                    parse_ceremony_output(closing(broken))
                self.assertIn("action_items[0].invitees", str(raised.exception))

    def test_error_names_the_offending_field(self) -> None:
        raw = '{"summary": "x", "action_items": [{"destination": "jira_comment", "target": "A-1"}]}'
        with self.assertRaises(OutputFormatError) as raised:
            parse_ceremony_output(raw)
        self.assertIn("action_items[0].title", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
