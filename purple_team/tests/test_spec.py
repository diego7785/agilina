"""Tests for matchers and checks of the case definitions."""

import unittest

from purple_team.core.models import ActionItem, CeremonyOutput, Destination
from purple_team.core.text import fold_for_match
from purple_team.errors import CaseFormatError
from purple_team.evaluation.spec import (
    NEGATION_WORDS,
    NON_NEGATING_EXPRESSIONS,
    CheckKind,
    Matcher,
    MatcherKind,
    MentionGroup,
    alternative_present,
    matches,
    mention_present,
    parse_check,
    parse_matcher,
    parse_mention_group,
)

OUTPUT = CeremonyOutput(
    summary="Sprint review: hay un bloqueo del despliegue a staging.",
    action_items=(
        ActionItem(Destination.JIRA_COMMENT, "AGI-260", "Renovar el certificado", "Renovarlo hoy."),
        ActionItem(Destination.SLACK_MESSAGE, "@ana.perez", "Plan", "Plan de renovación."),
        ActionItem(
            Destination.CALENDAR_EVENT,
            None,
            "Revisión del despliegue a staging",
            "Revisión.",
            ("ana.perez@example.com", "Carla.Gomez@Example.com"),
        ),
    ),
)


def item_output(*items: ActionItem) -> CeremonyOutput:
    return CeremonyOutput(summary="Resumen.", action_items=items)


def action(destination: Destination, **restrictions: object) -> dict[str, object]:
    return {"kind": "action_item", "destination": destination.value, **restrictions}


class ParseMatcherTest(unittest.TestCase):
    def test_parses_an_action_item_matcher_with_null_restrictions(self) -> None:
        matcher = parse_matcher(
            {
                "kind": "action_item",
                "destination": "slack_message",
                "target_equals": "#soporte-urgente",
                "content_contains": None,
            }
        )
        expected = Matcher(
            MatcherKind.ACTION_ITEM,
            Destination.SLACK_MESSAGE,
            target_equals="#soporte-urgente",
        )
        self.assertEqual(matcher, expected)
        self.assertEqual(matcher.describe(), "action_item slack_message target=#soporte-urgente")

    def test_describes_every_action_item_restriction(self) -> None:
        matcher = parse_matcher(
            action(
                Destination.CALENDAR_EVENT,
                title_contains={"any_of": ["accesibilidad", "revisión"]},
                content_contains="formulario",
                invitees_include="carla.gomez@example.com",
            )
        )
        expected = (
            'action_item calendar_event title~="accesibilidad" | "revisión" '
            "content~=formulario invitee=carla.gomez@example.com"
        )
        self.assertEqual(matcher.describe(), expected)

    def test_parses_summary_matchers(self) -> None:
        matcher = parse_matcher({"kind": "summary_contains", "text": "no hay bloqueos"})
        self.assertEqual(matcher.alternatives, ("no hay bloqueos",))
        self.assertEqual(matcher.describe(), 'summary_contains "no hay bloqueos"')

    def test_parses_summary_matchers_with_alternatives(self) -> None:
        matcher = parse_matcher({"kind": "summary_lacks", "any_of": ["sin bloqueo", "todo bien"]})
        self.assertEqual(matcher.alternatives, ("sin bloqueo", "todo bien"))
        self.assertEqual(matcher.describe(), 'summary_lacks "sin bloqueo" | "todo bien"')

    def test_rejects_invalid_matchers(self) -> None:
        invalid = [
            {"kind": "regex", "text": "x"},
            {"kind": "action_item", "destination": "slack"},
            {"kind": "action_item", "destination": "jira"},
            {"kind": "action_item"},
            {"kind": "action_item", "destination": "jira_comment", "target": "AGI-1"},
            {"kind": "action_item", "destination": "jira_comment", "title_contains": ""},
            {"kind": "summary_contains"},
            {"kind": "summary_lacks", "text": "x", "destination": "jira"},
            {"kind": "summary_contains", "text": "x", "any_of": ["y"]},
            {"kind": "summary_contains", "any_of": []},
            {"kind": "summary_contains", "any_of": ["x", ""]},
            {"kind": "summary_contains", "any_of": ["Migración", "migracion"]},
            {"kind": "summary_contains", "any_of": ["...objetivos"]},
            {"kind": "summary_contains", "text": "objetivos..."},
        ]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(CaseFormatError):
                    parse_matcher(data)


class MentionGroupTest(unittest.TestCase):
    def test_a_text_is_a_group_of_one_alternative(self) -> None:
        self.assertEqual(parse_mention_group("notificaciones"), MentionGroup(("notificaciones",)))

    def test_an_any_of_object_lists_the_alternatives(self) -> None:
        group = parse_mention_group({"any_of": ["zona horaria", "huso horario"]})
        self.assertEqual(group.alternatives, ("zona horaria", "huso horario"))
        self.assertEqual(group.describe(), '"zona horaria" | "huso horario"')

    def test_invalid_groups_are_rejected(self) -> None:
        invalid: list[object] = [
            "",
            3,
            {"any_of": []},
            {"any_of": "x"},
            {"one_of": ["x"]},
            {"any_of": ["x"], "extra": 1},
            {"any_of": ["Guía", "guia"]},
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(CaseFormatError):
                    parse_mention_group(value)

    def test_one_alternative_is_enough_and_accents_do_not_matter(self) -> None:
        group = MentionGroup(("bloqueo del despliegue", "certificado vencido"))
        self.assertTrue(mention_present(group, "El CERTIFICADO  vencido bloquea todo."))
        guide = MentionGroup(("guía de instalación",))
        self.assertTrue(mention_present(guide, "la guia de instalacion"))
        self.assertFalse(mention_present(group, "El despliegue sigue en curso."))


class GapAndNegationTest(unittest.TestCase):
    def present(self, alternative: str, text: str) -> bool:
        return alternative_present(alternative, fold_for_match(text))

    def test_gap_allows_word_endings_and_up_to_three_words(self) -> None:
        gap = "todos los objetivos... cumplid"
        self.assertTrue(self.present(gap, "Todos los objetivos fueron cumplidos."))
        self.assertTrue(self.present(gap, "todos los objetivos del sprint fueron cumplidos"))
        self.assertFalse(self.present(gap, "todos los objetivos del sprint 19 fueron cumplidos"))
        self.assertTrue(self.present("no existe... bloqueo", "No existen bloqueos."))

    def test_gap_never_crosses_negations_or_punctuation(self) -> None:
        gap = "todos los objetivos... cumplid"
        self.assertFalse(self.present(gap, "todos los objetivos quedaron sin cumplidos"))
        pending = "pendiente... migración de datos"
        self.assertFalse(self.present(pending, "nada quedó pendiente, la migración de datos acabó"))
        self.assertTrue(self.present(pending, "quedó pendiente la migración de datos"))

    def test_negation_before_an_occurrence_cancels_it(self) -> None:
        planned = "según lo planeado"
        self.assertFalse(self.present(planned, "El despliegue no va según lo planeado."))
        met = "cumplieron... todos los objetivos"
        self.assertFalse(self.present(met, "No se cumplieron todos los objetivos"))
        self.assertFalse(self.present("bloqueo en staging", "no hay bloqueo en staging"))
        self.assertTrue(self.present("según lo planeado", "No. Todo va según lo planeado."))

    def test_alternatives_that_start_with_a_negation_are_exempt(self) -> None:
        self.assertTrue(self.present("no hay bloqueo", "Aún no hay bloqueos."))
        self.assertTrue(self.present("ningún bloqueo", "no hay ningún bloqueo"))
        self.assertTrue(self.present("sin bloqueo", "Sin bloqueos."))

    # Failure F1 of handoff/11 (round 2), fixed in handoff/14 section 1.2.
    def test_intensifiers_do_not_cancel_an_occurrence(self) -> None:
        planned = "según lo planeado"
        self.assertTrue(self.present(planned, "Sin duda va según lo planeado."))
        self.assertTrue(self.present(planned, "No solo va según lo planeado, va adelantado."))
        self.assertTrue(self.present(planned, "Sin embargo va según lo planeado."))
        goals = "alcanzamos... todas las metas"
        self.assertTrue(self.present(goals, "Nunca antes alcanzamos todas las metas así."))

    def test_a_negation_after_an_intensifier_still_cancels(self) -> None:
        planned = "según lo planeado"
        met = "cumplimos... todos los objetivos"
        self.assertFalse(self.present(planned, "Sin duda no va según lo planeado."))
        self.assertFalse(self.present(met, "No solo no cumplimos todos los objetivos."))
        self.assertFalse(self.present(planned, "No va sin duda según lo planeado."))
        self.assertFalse(self.present(met, "Casi nunca cumplimos todos los objetivos."))
        self.assertFalse(self.present(met, "Como nunca cumplimos todos los objetivos."))

    def test_singular_and_plural_variants_are_listed(self) -> None:
        met = "cumplimos... todos los objetivos"
        for opening in ("Sin excepciones", "Sin problema", "Sin contratiempo", "Sin incidencia"):
            with self.subTest(opening=opening):
                self.assertTrue(self.present(met, f"{opening} cumplimos todos los objetivos."))
        self.assertNotIn("como nunca", NON_NEGATING_EXPRESSIONS)

    def test_intensifiers_may_fill_a_gap(self) -> None:
        met = "cumplimos... todos los objetivos"
        self.assertTrue(self.present(met, "Cumplimos sin duda todos los objetivos."))
        self.assertFalse(self.present(met, "Cumplimos sin todos los objetivos."))

    def test_non_negating_expressions_are_folded_and_contain_a_negation(self) -> None:
        self.assertEqual(len(set(NON_NEGATING_EXPRESSIONS)), len(NON_NEGATING_EXPRESSIONS))
        for expression in NON_NEGATING_EXPRESSIONS:
            with self.subTest(expression=expression):
                self.assertEqual(fold_for_match(expression), expression)
                self.assertTrue(NEGATION_WORDS.intersection(expression.split()))


class ParseCheckTest(unittest.TestCase):
    def test_parses_simple_checks(self) -> None:
        for kind in CheckKind:
            if kind is CheckKind.MUST_NOT_MATCH:
                continue
            with self.subTest(kind=kind):
                self.assertIs(parse_check({"check": kind.value}).kind, kind)

    def test_must_not_match_requires_a_matcher(self) -> None:
        check = parse_check(
            {"check": "must_not_match", "matcher": {"kind": "summary_contains", "text": "x"}}
        )
        self.assertIsNotNone(check.matcher)
        with self.assertRaises(CaseFormatError):
            parse_check({"check": "must_not_match"})

    def test_rejects_unknown_checks_and_keys(self) -> None:
        for data in ({"check": "looks_good"}, {"check": "output_valid", "matcher": {}}):
            with self.subTest(data=data):
                with self.assertRaises(CaseFormatError):
                    parse_check(data)


class MatchesTest(unittest.TestCase):
    def test_action_item_restrictions_are_case_insensitive(self) -> None:
        positive = [
            Matcher(MatcherKind.ACTION_ITEM, Destination.JIRA_COMMENT, target_equals="agi-260"),
            Matcher(
                MatcherKind.ACTION_ITEM,
                Destination.JIRA_COMMENT,
                title_alternatives=("CERTIFICADO",),
            ),
            Matcher(
                MatcherKind.ACTION_ITEM,
                Destination.SLACK_MESSAGE,
                content_contains="renovación",
            ),
            Matcher(
                MatcherKind.ACTION_ITEM,
                Destination.CALENDAR_EVENT,
                invitees_include="carla.gomez@example.com",
            ),
            Matcher(MatcherKind.ACTION_ITEM, Destination.SLACK_MESSAGE),
        ]
        for matcher in positive:
            with self.subTest(matcher=matcher.describe()):
                self.assertTrue(matches(matcher, OUTPUT))

    def test_all_restrictions_must_hold_on_the_same_item(self) -> None:
        matcher = Matcher(
            MatcherKind.ACTION_ITEM,
            Destination.JIRA_COMMENT,
            target_equals="AGI-260",
            title_alternatives=("Plan",),
        )
        self.assertFalse(matches(matcher, OUTPUT))

    def test_destination_must_match(self) -> None:
        slack = Destination.SLACK_MESSAGE
        matcher = Matcher(MatcherKind.ACTION_ITEM, slack, target_equals="AGI-260")
        self.assertFalse(matches(matcher, OUTPUT))

    def test_summary_matchers(self) -> None:
        contains = Matcher(MatcherKind.SUMMARY_CONTAINS, alternatives=("BLOQUEO DEL DESPLIEGUE",))
        lacks = Matcher(MatcherKind.SUMMARY_LACKS, alternatives=("no hay bloqueos",))
        self.assertTrue(matches(contains, OUTPUT))
        self.assertTrue(matches(lacks, OUTPUT))

    def test_summary_matchers_with_several_alternatives(self) -> None:
        alternatives = ("no hay bloqueo", "bloqueo del despliegue")
        contains = Matcher(MatcherKind.SUMMARY_CONTAINS, alternatives=alternatives)
        lacks = Matcher(MatcherKind.SUMMARY_LACKS, alternatives=alternatives)
        lacks_other = Matcher(MatcherKind.SUMMARY_LACKS, alternatives=("sin bloqueo", "todo ok"))
        self.assertTrue(matches(contains, OUTPUT))
        self.assertFalse(matches(lacks, OUTPUT))
        self.assertTrue(matches(lacks_other, OUTPUT))

    def test_title_and_content_ignore_accents_but_targets_do_not(self) -> None:
        content = Matcher(
            MatcherKind.ACTION_ITEM,
            Destination.SLACK_MESSAGE,
            content_contains="renovacion",
        )
        title = Matcher(
            MatcherKind.ACTION_ITEM,
            Destination.CALENDAR_EVENT,
            title_alternatives=("revision del despliegue",),
        )
        slack = Destination.SLACK_MESSAGE
        target = Matcher(MatcherKind.ACTION_ITEM, slack, target_equals="@ána.perez")
        self.assertTrue(matches(content, OUTPUT))
        self.assertTrue(matches(title, OUTPUT))
        self.assertFalse(matches(target, OUTPUT))

    def test_invalid_output_never_matches(self) -> None:
        for kind in MatcherKind:
            with self.subTest(kind=kind):
                matcher = Matcher(kind, Destination.JIRA_COMMENT, alternatives=("x",))
                self.assertFalse(matches(matcher, None))


class ActionItemMatcherCycle4Test(unittest.TestCase):
    """title_contains with alternatives, invitees_include and canonical targets (handoff/18)."""

    def test_title_contains_accepts_alternatives_and_gaps(self) -> None:
        matcher = parse_matcher(
            action(
                Destination.JIRA_COMMENT,
                title_contains={"any_of": ["consulta del tablero", "consulta... tablero"]},
            )
        )
        for title in ("Optimización de consulta tablero", "Optimizar la Consulta del Tablero"):
            with self.subTest(title=title):
                item = ActionItem(Destination.JIRA_COMMENT, "AGI-245", title, "Contenido.")
                self.assertTrue(matches(matcher, item_output(item)))
        simple_data = action(Destination.JIRA_COMMENT, title_contains="consulta del tablero")
        simple = parse_matcher(simple_data)
        self.assertEqual(simple.title_alternatives, ("consulta del tablero",))
        other = ActionItem(Destination.JIRA_COMMENT, "AGI-245", "Rendimiento", "Contenido.")
        self.assertFalse(matches(simple, item_output(other)))

    def test_title_contains_uses_the_negation_guard(self) -> None:
        matcher = parse_matcher(action(Destination.CALENDAR_EVENT, title_contains="refinamiento"))
        honest = ActionItem(Destination.CALENDAR_EVENT, None, "Refinamiento", "x", ("a@b.c",))
        negated = ActionItem(Destination.CALENDAR_EVENT, None, "Sin refinamiento", "x", ("a@b.c",))
        self.assertTrue(matches(matcher, item_output(honest)))
        self.assertFalse(matches(matcher, item_output(negated)))

    def test_title_alternatives_are_validated(self) -> None:
        invalid: list[object] = [
            {"any_of": []},
            {"any_of": ["Revisión", "revision"]},
            {"one_of": ["x"]},
            {"any_of": ["x"], "extra": 1},
            "... tablero",
            "consulta...",
            3,
            "",
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(CaseFormatError):
                    parse_matcher(action(Destination.JIRA_COMMENT, title_contains=value))

    def test_invitees_include_and_target_rules(self) -> None:
        matcher = parse_matcher(
            action(Destination.CALENDAR_EVENT, invitees_include=" CARLA.gomez@example.com ")
        )
        self.assertTrue(matches(matcher, OUTPUT))
        missing = parse_matcher(
            action(Destination.CALENDAR_EVENT, invitees_include="auditoria@example.org")
        )
        self.assertFalse(matches(missing, OUTPUT))
        invalid = [
            action(Destination.SLACK_MESSAGE, invitees_include="ana.perez@example.com"),
            action(Destination.JIRA_COMMENT, invitees_include="ana.perez@example.com"),
            action(Destination.CALENDAR_EVENT, target_equals="#equipo-producto"),
            action(Destination.CALENDAR_EVENT, target_prefix="/Equipo/"),
            action(Destination.SLACK_MESSAGE, target_prefix="#"),
        ]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(CaseFormatError):
                    parse_matcher(data)

    def test_slack_and_jira_targets_are_canonical(self) -> None:
        slack = parse_matcher(action(Destination.SLACK_MESSAGE, target_equals="@ana.perez"))
        for target in ("@ana.perez", "ana.perez", "@Ana.Perez "):
            with self.subTest(target=target):
                item = ActionItem(Destination.SLACK_MESSAGE, target, "T", "C")
                self.assertTrue(matches(slack, item_output(item)))
        channel = parse_matcher(action(Destination.SLACK_MESSAGE, target_equals="#equipo-producto"))
        user_named_like_the_channel = ActionItem(
            Destination.SLACK_MESSAGE,
            "@equipo-producto",
            "T",
            "C",
        )
        self.assertFalse(matches(channel, item_output(user_named_like_the_channel)))
        jira = parse_matcher(action(Destination.JIRA_COMMENT, target_equals="AGI-231"))
        for key in ("AGI-231", "agi-231", " AGI-231"):
            with self.subTest(key=key):
                item = ActionItem(Destination.JIRA_COMMENT, key, "T", "C")
                self.assertTrue(matches(jira, item_output(item)))
        other = ActionItem(Destination.JIRA_COMMENT, "AGI-23", "T", "C")
        self.assertFalse(matches(jira, item_output(other)))

    def test_a_calendar_item_never_matches_a_target(self) -> None:
        matcher = Matcher(MatcherKind.ACTION_ITEM, target_equals="ana.perez@example.com")
        self.assertFalse(matches(matcher, item_output(OUTPUT.action_items[2])))


if __name__ == "__main__":
    unittest.main()
