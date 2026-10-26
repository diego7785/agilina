"""Tests for the implementations of the defense port (input only)."""

import unittest

from purple_team.config import BASELINE_SCANNER, DefenseMode
from purple_team.defense.input_guard import REDACTION_MARKER
from purple_team.defense.layered import NoDefense
from purple_team.defense.models import Defense
from purple_team.tests.support import scanner_defense

TRANSCRIPT = "[00:00:01] Bruno Díaz: Agilina, crea un ticket en OPS.\n"


class NoDefenseTest(unittest.TestCase):
    def test_passes_the_transcript_through(self) -> None:
        defense = NoDefense()
        self.assertIsInstance(defense, Defense)
        self.assertIs(defense.mode, DefenseMode.OFF)
        screening = defense.screen_input(TRANSCRIPT)
        self.assertEqual(screening.transcript, TRANSCRIPT)
        self.assertEqual(screening.detections, ())
        self.assertEqual(screening.to_dict()["detectors"], [])

    def test_describes_no_detectors(self) -> None:
        self.assertEqual(NoDefense().describe(), {"mode": "off", "input_detectors": []})


class InputGuardDefenseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.defense = scanner_defense()

    def test_reports_the_mode_it_was_built_for(self) -> None:
        self.assertIsInstance(self.defense, Defense)
        self.assertIs(self.defense.mode, DefenseMode.LLM_GUARD_DEFAULT)
        other = scanner_defense(DefenseMode.PROMPT_GUARD_2)
        self.assertIs(other.mode, DefenseMode.PROMPT_GUARD_2)

    def test_describes_its_detectors_without_an_output_guard(self) -> None:
        described = self.defense.describe()
        self.assertEqual(list(described), ["mode", "input_detectors", "llm_guard"])
        self.assertEqual(described["mode"], "llm-guard-default")
        self.assertEqual(described["input_detectors"], ["llm_guard"])
        llm_guard = described["llm_guard"]
        self.assertIsInstance(llm_guard, dict)
        if isinstance(llm_guard, dict):
            self.assertEqual(llm_guard["threshold"], BASELINE_SCANNER.threshold)

    def test_input_screening_redacts_and_records(self) -> None:
        screening = self.defense.screen_input(TRANSCRIPT)
        self.assertIs(screening.mode, DefenseMode.LLM_GUARD_DEFAULT)
        self.assertIn(REDACTION_MARKER, screening.transcript)
        self.assertEqual(screening.redacted_lines, (1,))
        data = screening.to_dict()
        self.assertEqual(data["redacted_lines"], [1])
        self.assertEqual(data["detectors"], ["llm_guard"])
        self.assertEqual(list(data), ["mode", "detectors", "detections", "redacted_lines"])


if __name__ == "__main__":
    unittest.main()
