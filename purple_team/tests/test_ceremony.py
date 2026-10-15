"""Tests for the core that closes the ceremony."""

import json
import unittest
from pathlib import Path

from purple_team.core.ceremony import CeremonyCloser
from purple_team.core.prompts import (
    CLOSING_REQUEST,
    TEAM_CONTEXT_CLOSE,
    TEAM_CONTEXT_OPEN,
    TRANSCRIPT_CLOSE,
    TRANSCRIPT_OPEN,
    SystemPrompt,
    build_user_content,
    load_system_prompt,
)
from purple_team.errors import ConfigError
from purple_team.providers.base import ModelRequest, ModelResponse, RequestTrace
from purple_team.tests.support import REAL_SYSTEM_PROMPT, make_temp_dir, real_team_context

TRACE = RequestTrace(run_id="run-1", case_id="c00-control")
PROMPT = SystemPrompt(text="Eres Agilina.", sha256="abc", source=Path("prompt.txt"))
VALID_ANSWER = json.dumps({"summary": "Todo en orden.", "action_items": []})
CONTEXT = real_team_context()


class RecordingProvider:
    """Fake provider that returns a fixed text and remembers the requests."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.requests: list[ModelRequest] = []

    @property
    def name(self) -> str:
        """Provider name."""
        return "fake"

    @property
    def model(self) -> str:
        """Model name."""
        return "fake-model"

    def ensure_available(self) -> None:
        """Always available."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Record the request and return the fixed answer."""
        self.requests.append(request)
        return ModelResponse(text=self.answer, provider=self.name, model=self.model)


class PromptsTest(unittest.TestCase):
    def test_user_content_has_the_context_block_then_the_transcript_block(self) -> None:
        content = build_user_content("[00:00:01] Ana Pérez: Hola.\n", CONTEXT)
        expected = [
            TEAM_CONTEXT_OPEN,
            *CONTEXT.render_for_model().split("\n"),
            TEAM_CONTEXT_CLOSE,
            "",
            TRANSCRIPT_OPEN,
            "[00:00:01] Ana Pérez: Hola.",
            TRANSCRIPT_CLOSE,
            "",
            CLOSING_REQUEST,
        ]
        self.assertEqual(content.split("\n"), expected)

    def test_context_comes_before_the_transcript_and_lists_the_members(self) -> None:
        content = build_user_content("[00:00:01] Ana Pérez: Hola.", CONTEXT)
        self.assertLess(content.index(TEAM_CONTEXT_CLOSE), content.index(TRANSCRIPT_OPEN))
        context_block = content[: content.index(TEAM_CONTEXT_CLOSE)]
        for value in (*CONTEXT.member_emails, *CONTEXT.member_slack_users):
            self.assertIn(value, context_block)
        for key in CONTEXT.jira_issue_keys:
            self.assertIn(f'"key": "{key}"', context_block)
        self.assertIn('"slack_channel": "#equipo-producto"', context_block)
        self.assertIn('"jira_project_key": "AGI"', context_block)
        self.assertIn('"onedrive_folder": "/Equipo/Ceremonias/"', context_block)

    def test_versioned_prompt_declares_both_blocks(self) -> None:
        text = load_system_prompt(REAL_SYSTEM_PROMPT).text
        for marker in (TEAM_CONTEXT_OPEN, TEAM_CONTEXT_CLOSE, TRANSCRIPT_OPEN, TRANSCRIPT_CLOSE):
            self.assertIn(marker, text)
        self.assertIn("no confiable", text)

    def test_versioned_prompt_names_the_three_destinations(self) -> None:
        text = load_system_prompt(REAL_SYSTEM_PROMPT).text
        for destination in ("jira_comment", "calendar_event", "slack_message"):
            self.assertIn(f'"{destination}"', text)
        self.assertIn("invitees", text)
        for old_destination in ('"jira"', '"email"', '"onedrive"'):
            self.assertNotIn(old_destination, text)

    def test_loads_the_versioned_prompt_with_its_hash(self) -> None:
        prompt = load_system_prompt(REAL_SYSTEM_PROMPT)
        self.assertIn("Eres Agilina", prompt.text)
        self.assertEqual(len(prompt.sha256), 64)

    def test_missing_or_empty_prompt_is_a_config_error(self) -> None:
        tmp_dir = make_temp_dir(self)
        empty = tmp_dir / "empty.txt"
        empty.write_text("  \n", encoding="utf-8")
        for path in (tmp_dir / "missing.txt", empty):
            with self.subTest(path=path.name):
                with self.assertRaises(ConfigError):
                    load_system_prompt(path)


class CeremonyCloserTest(unittest.TestCase):
    def test_sends_prompt_transcript_trace_and_temperature(self) -> None:
        provider = RecordingProvider(VALID_ANSWER)
        closer = CeremonyCloser(provider, temperature=0.25, team_context=CONTEXT)
        closing = closer.close("hola", PROMPT, TRACE)
        request = provider.requests[0]
        self.assertEqual(request.system_prompt, "Eres Agilina.")
        self.assertEqual(request.user_content, build_user_content("hola", CONTEXT))
        self.assertEqual(request.trace, TRACE)
        self.assertEqual(request.temperature, 0.25)
        self.assertEqual(closing.request, request)

    def test_returns_the_parsed_output(self) -> None:
        closer = CeremonyCloser(RecordingProvider(VALID_ANSWER), 0.0, CONTEXT)
        closing = closer.close("x", PROMPT, TRACE)
        self.assertIsNotNone(closing.output)
        self.assertIsNone(closing.parse_error)
        self.assertEqual(closing.response.text, VALID_ANSWER)

    def test_invalid_output_is_reported_without_raising(self) -> None:
        provider = RecordingProvider("no es JSON")
        closing = CeremonyCloser(provider, 0.0, CONTEXT).close("x", PROMPT, TRACE)
        self.assertIsNone(closing.output)
        self.assertIsNotNone(closing.parse_error)
        self.assertEqual(closing.response.text, "no es JSON")


if __name__ == "__main__":
    unittest.main()
