"""Tests for the team context: versioned file, validations and what the model receives."""

import json
import unittest
from collections.abc import Callable
from pathlib import Path

from purple_team.cases import load_cases
from purple_team.core.text import fold_for_match
from purple_team.errors import ConfigError
from purple_team.evaluation.spec import MatcherKind, alternative_present
from purple_team.paths import display_path
from purple_team.team_context import load_team_context
from purple_team.tests.support import (
    KEYWORD_SCANNER_WORDS,
    PURPLE_TEAM_DIR,
    REAL_CASES_DIR,
    REAL_TEAM_CONTEXT,
    make_temp_dir,
)

type Mutation = Callable[[dict[str, object]], None]

EXPECTED_EMAILS = (
    "ana.perez@example.com",
    "bruno.diaz@example.com",
    "carla.gomez@example.com",
    "elena.ruiz@example.com",
)
EXPECTED_SLACK_USERS = ("@ana.perez", "@bruno.diaz", "@carla.gomez", "@elena.ruiz")
EXPECTED_ISSUE_KEYS = (
    "AGI-189",
    "AGI-198",
    "AGI-214",
    "AGI-231",
    "AGI-245",
    "AGI-252",
    "AGI-260",
    "AGI-277",
)
MODEL_VIEW_KEYS = [
    "team_name",
    "members",
    "slack_channel",
    "jira_project_key",
    "jira_issues",
    "onedrive_folder",
]


def versioned_data() -> dict[str, object]:
    data = json.loads(REAL_TEAM_CONTEXT.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("team context")
    return data


def first_entry(data: dict[str, object], key: str) -> dict[str, object]:
    entries = data[key]
    if not isinstance(entries, list) or not isinstance(entries[0], dict):
        raise TypeError(key)
    return entries[0]


def first_member(data: dict[str, object]) -> dict[str, object]:
    return first_entry(data, "members")


def first_issue(data: dict[str, object]) -> dict[str, object]:
    return first_entry(data, "jira_issues")


class VersionedTeamContextTest(unittest.TestCase):
    def test_loads_the_versioned_file(self) -> None:
        context = load_team_context(REAL_TEAM_CONTEXT)
        self.assertEqual(context.member_emails, EXPECTED_EMAILS)
        self.assertEqual(context.member_slack_users, EXPECTED_SLACK_USERS)
        self.assertEqual(context.slack_channel, "#equipo-producto")
        self.assertEqual(context.jira_project_key, "AGI")
        self.assertEqual(context.jira_issue_keys, EXPECTED_ISSUE_KEYS)
        self.assertEqual(context.onedrive_folder, "/Equipo/Ceremonias/")
        self.assertEqual(len(context.sha256), 64)

    def test_every_email_uses_the_reserved_team_domain(self) -> None:
        for email in load_team_context(REAL_TEAM_CONTEXT).member_emails:
            with self.subTest(email=email):
                self.assertTrue(email.endswith("@example.com"))

    def test_render_for_model_is_deterministic_and_lists_every_member(self) -> None:
        context = load_team_context(REAL_TEAM_CONTEXT)
        rendered = context.render_for_model()
        self.assertEqual(rendered, load_team_context(REAL_TEAM_CONTEXT).render_for_model())
        self.assertEqual(json.loads(rendered), context.model_view())
        self.assertEqual(list(context.model_view()), MODEL_VIEW_KEYS)
        for value in (*EXPECTED_EMAILS, *EXPECTED_SLACK_USERS, *EXPECTED_ISSUE_KEYS):
            self.assertIn(value, rendered)
        self.assertIn("Ana Pérez", rendered)
        self.assertIn("#equipo-producto", rendered)
        self.assertIn("/Equipo/Ceremonias/", rendered)
        self.assertNotIn(str(PURPLE_TEAM_DIR), rendered)

    def test_record_uses_a_relative_path_with_the_default_layout(self) -> None:
        context = load_team_context(REAL_TEAM_CONTEXT)
        record = context.to_record(lambda path: display_path(path, PURPLE_TEAM_DIR))
        self.assertEqual(record["file"], "team_context.json")
        self.assertEqual(record["sha256"], context.sha256)
        self.assertEqual(record["jira_project_key"], "AGI")
        self.assertEqual(record["slack_channel"], "#equipo-producto")

    def test_context_never_contains_mentions_or_indicators(self) -> None:
        """The context must not make up for what an input guard redacts (handoff/19, B1).

        No summary mention and no summary indicator of any case occurs in the rendered
        context, no content or invitee indicator is a substring of it and no keyword of the
        test doubles appears in it.
        """
        folded = fold_for_match(load_team_context(REAL_TEAM_CONTEXT).render_for_model())
        for case in load_cases(REAL_CASES_DIR):
            alternatives = [
                alternative
                for group in case.expected.summary_mentions
                for alternative in group.alternatives
            ]
            literals: list[str] = []
            indicators = case.injection.effect_indicators if case.injection is not None else ()
            for indicator in indicators:
                if indicator.kind is MatcherKind.ACTION_ITEM:
                    values = (indicator.content_contains, indicator.invitees_include)
                    literals.extend(value for value in values if value is not None)
                else:
                    alternatives.extend(indicator.alternatives)
            for alternative in alternatives:
                with self.subTest(case=case.case_id, alternative=alternative):
                    self.assertFalse(alternative_present(alternative, folded))
            for literal in literals:
                with self.subTest(case=case.case_id, literal=literal):
                    self.assertNotIn(fold_for_match(literal), folded)
        for word in KEYWORD_SCANNER_WORDS:
            self.assertNotIn(word, folded)


class BrokenTeamContextTest(unittest.TestCase):
    def write(self, data: object) -> Path:
        path = make_temp_dir(self) / "team_context.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def assert_rejected(self, mutation: Mutation) -> ConfigError:
        data = versioned_data()
        mutation(data)
        with self.assertRaises(ConfigError) as raised:
            load_team_context(self.write(data))
        return raised.exception

    def test_missing_file_and_invalid_json_are_config_errors(self) -> None:
        tmp_dir = make_temp_dir(self)
        with self.assertRaises(ConfigError):
            load_team_context(tmp_dir / "missing.json")
        broken = tmp_dir / "broken.json"
        broken.write_text("{ no es json", encoding="utf-8")
        with self.assertRaises(ConfigError) as raised:
            load_team_context(broken)
        self.assertIsInstance(raised.exception.__cause__, json.JSONDecodeError)

    def test_top_level_must_be_an_object_with_exact_keys(self) -> None:
        with self.assertRaises(ConfigError):
            load_team_context(self.write([1, 2]))
        self.assert_rejected(lambda data: data.update(extra="x"))
        self.assert_rejected(lambda data: data.__delitem__("team_name"))
        self.assert_rejected(lambda data: data.__delitem__("slack_channel"))
        self.assert_rejected(lambda data: data.__delitem__("jira_issues"))
        self.assert_rejected(lambda data: data.update(schema_version=3))
        self.assert_rejected(lambda data: data.update(schema_version=True))

    def test_version_one_is_rejected_with_a_migration_message(self) -> None:
        error = self.assert_rejected(lambda data: data.update(schema_version=1))
        message = str(error)
        self.assertIn("schema_version 1 ya no se admite", message)
        self.assertIn("slack_user", message)
        self.assertIn("slack_channel", message)
        self.assertIn("jira_issues", message)

    def test_members_must_be_valid_and_unique(self) -> None:
        self.assert_rejected(lambda data: data.update(members=[]))
        self.assert_rejected(lambda data: data.update(members=["Ana"]))
        self.assert_rejected(lambda data: first_member(data).update(extra="x"))
        self.assert_rejected(lambda data: first_member(data).__delitem__("slack_user"))
        self.assert_rejected(lambda data: first_member(data).update(role=""))
        self.assert_rejected(lambda data: first_member(data).update(email="ana.perez"))
        self.assert_rejected(lambda data: first_member(data).update(email="a b@example.com"))
        self.assert_rejected(
            lambda data: first_member(data).update(email="BRUNO.DIAZ@example.com"),
        )
        self.assert_rejected(lambda data: first_member(data).update(name="Bruno Díaz"))
        self.assert_rejected(lambda data: first_member(data).update(slack_user="@bruno.diaz"))

    def test_slack_user_and_channel_follow_the_slack_form(self) -> None:
        for user in ("ana.perez", "@Ana.Perez", "@ana perez", "#ana.perez", "@" + "a" * 81):
            with self.subTest(user=user):
                self.assert_rejected(
                    lambda data, user=user: first_member(data).update(slack_user=user),
                )
        for channel in ("equipo-producto", "#Equipo", "#equipo producto", "@equipo", "#"):
            with self.subTest(channel=channel):
                self.assert_rejected(
                    lambda data, channel=channel: data.update(slack_channel=channel),
                )

    def test_jira_issues_must_be_valid_unique_keys_of_the_project(self) -> None:
        self.assert_rejected(lambda data: data.update(jira_issues=[]))
        self.assert_rejected(lambda data: data.update(jira_issues=["AGI-1"]))
        self.assert_rejected(lambda data: first_issue(data).update(extra="x"))
        self.assert_rejected(lambda data: first_issue(data).update(title=" "))
        self.assert_rejected(lambda data: first_issue(data).update(key="AGI-198"))
        for key in ("OPS-12", "AGI-0", "AGI-01", "agi-189", "AGI 189", "AGI"):
            with self.subTest(key=key):
                self.assert_rejected(lambda data, key=key: first_issue(data).update(key=key))

    def test_jira_key_and_onedrive_folder_are_validated(self) -> None:
        for key in ("agi", "A", "AGI-1", "ABCDEFGHIJK"):
            with self.subTest(key=key):
                self.assert_rejected(lambda data, key=key: data.update(jira_project_key=key))
        for folder in ("Equipo/Ceremonias/", "/Equipo/Ceremonias", "/Equipo/../Otro/"):
            with self.subTest(folder=folder):
                self.assert_rejected(
                    lambda data, folder=folder: data.update(onedrive_folder=folder),
                )


if __name__ == "__main__":
    unittest.main()
