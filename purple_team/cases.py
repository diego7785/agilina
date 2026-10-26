"""Loader and validator of the synthetic test cases (one folder per case under ``cases/``)."""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn

from purple_team.atlas import ATLAS_CATALOG, AtlasTechnique
from purple_team.core.models import CeremonyOutput, Destination, canonical_target
from purple_team.core.output_parser import OutputFormatError, parse_ceremony_output
from purple_team.errors import CaseFormatError
from purple_team.evaluation.spec import (
    Check,
    Matcher,
    MatcherKind,
    MentionGroup,
    matches,
    mention_present,
    parse_check,
    parse_matcher,
    parse_mention_group,
)
from purple_team.policy import SystemPolicy
from purple_team.providers.mock import MockScript

CASE_ID_PATTERN: Final = re.compile(r"^c\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
CASE_SCHEMA_VERSION: Final = 3
# Versions that are no longer accepted, with what to change (cycle 4 changed the action model).
LEGACY_SCHEMA_MESSAGES: Final = {
    1: (
        "usa 3, añade atlas_techniques y describe los action items con jira_comment, "
        "calendar_event y slack_message (README §6.2)"
    ),
    2: (
        "el ciclo 4 cambió el modelo de acciones (jira_comment, calendar_event, "
        "slack_message); usa 3 (README §6.2)"
    ),
}
SUMMARY_TAMPERING_GOAL: Final = "summary_tampering"
CASE_FILE_NAME: Final = "case.json"
LANGUAGES: Final = frozenset({"es", "en"})
CEREMONIES: Final = frozenset({"daily", "sprint_review", "retrospective", "sprint_planning"})
TECHNIQUES: Final = frozenset(
    {
        "override_instruction",
        "assistant_addressed_note",
        "vocative_command",
        "indirect_english",
        "speaker_voiced_request",
        "hidden_markup",
    }
)
GOALS: Final = frozenset(
    {
        "slack_exfiltration",
        "calendar_exfiltration",
        "summary_tampering",
        "fraudulent_jira_comment",
    }
)
TOP_LEVEL_KEYS: Final = frozenset(
    {
        "schema_version",
        "id",
        "title",
        "description",
        "language",
        "ceremony",
        "transcript_file",
        "atlas_techniques",
        "injection",
        "expected_result",
        "pass_criterion",
        "mock",
    }
)
INJECTION_KEYS: Final = frozenset({"technique", "goal", "payload", "effect_indicators"})
EXPECTED_KEYS: Final = frozenset({"description", "summary_mentions", "action_items"})
CRITERION_KEYS: Final = frozenset({"description", "checks"})
MOCK_KEYS: Final = frozenset({"benign_response_file", "injected_response_file"})


@dataclass(frozen=True, slots=True)
class Injection:
    """Instruction hidden in the transcript and how to recognize that it had an effect."""

    technique: str
    goal: str
    payload: str
    effect_indicators: tuple[Matcher, ...]


@dataclass(frozen=True, slots=True)
class ExpectedResult:
    """What a correct and safe closing contains."""

    description: str
    summary_mentions: tuple[MentionGroup, ...]
    action_items: tuple[Matcher, ...]


@dataclass(frozen=True, slots=True)
class PassCriterion:
    """Natural-language criterion and its evaluable checks."""

    description: str
    checks: tuple[Check, ...]


@dataclass(frozen=True, slots=True)
class Case:
    """A validated test case."""

    case_id: str
    title: str
    description: str
    language: str
    ceremony: str
    directory: Path
    transcript_path: Path
    transcript: str
    atlas_techniques: tuple[AtlasTechnique, ...]
    injection: Injection | None
    expected: ExpectedResult
    criterion: PassCriterion
    mock_script: MockScript | None
    raw_definition: Mapping[str, object]


def load_cases(cases_dir: Path, selected_ids: Sequence[str] = ()) -> tuple[Case, ...]:
    """Load and validate every case (sorted by id); keep only ``selected_ids`` if given."""
    if not cases_dir.is_dir():
        raise CaseFormatError(f"No existe la carpeta de casos {cases_dir}")
    folders = [path for path in sorted(cases_dir.iterdir()) if _is_case_folder(path)]
    cases = tuple(_load_case(folder) for folder in folders)
    if not cases:
        raise CaseFormatError(f"La carpeta {cases_dir} no contiene casos")
    if not selected_ids:
        return cases
    known = {case.case_id for case in cases}
    unknown = sorted(set(selected_ids) - known)
    if unknown:
        names = ", ".join(unknown)
        raise CaseFormatError(f"Casos desconocidos: {names}")
    wanted = set(selected_ids)
    return tuple(case for case in cases if case.case_id in wanted)


def validate_against_policy(
    cases: Sequence[Case],
    policy: SystemPolicy,
    known_issue_keys: frozenset[str],
) -> None:
    """Raise ``CaseFormatError`` if an expected item is unreachable or a benign item is blocked.

    It uses the very predicate of the system policy: an expected destination that the policy
    would block could never be produced by a correct and safe closing. Oracle 10: every
    expected ``jira_comment`` names an issue listed in the team context (``known_issue_keys``,
    canonical keys), so the model sees the issue the case expects; it is not the predicate of
    the policy, which allows any issue of the project.
    """
    for case in cases:
        where = f"{case.case_id}/{CASE_FILE_NAME}"
        for matcher in case.expected.action_items:
            problem = _unreachable(matcher, policy)
            if problem is not None:
                raise CaseFormatError(f"{where}: {matcher.describe()} es inalcanzable ({problem})")
            if not _known_issue(matcher, known_issue_keys):
                message = (
                    f"{where}: {matcher.describe()} no es una incidencia del contexto del equipo "
                    "(jira_issues)"
                )
                raise CaseFormatError(message)
        if case.mock_script is None:
            continue
        benign = _parse_fixture(case.mock_script.benign_response, f"{where} (mock benigno)")
        for index, item in enumerate(benign.action_items):
            reason = policy.block_reason(item)
            if reason is not None:
                message = (
                    f"{where}: la respuesta benigna tiene un action item bloqueado "
                    f"(action_items[{index}], {reason.value})"
                )
                raise CaseFormatError(message)


def _unreachable(matcher: Matcher, policy: SystemPolicy) -> str | None:
    destination = matcher.destination
    if destination is None:
        return None
    if matcher.target_equals is not None and destination is not Destination.CALENDAR_EVENT:
        reason = policy.target_block_reason(destination, matcher.target_equals)
        if reason is not None:
            return reason.value
    if matcher.invitees_include is not None:
        reason = policy.invitee_block_reason(matcher.invitees_include)
        if reason is not None:
            return reason.value
    return None


def _known_issue(matcher: Matcher, known_issue_keys: frozenset[str]) -> bool:
    """Oracle 10: an expected ``jira_comment`` with a target names a listed issue."""
    if matcher.destination is not Destination.JIRA_COMMENT or matcher.target_equals is None:
        return True
    return canonical_target(Destination.JIRA_COMMENT, matcher.target_equals) in known_issue_keys


def mock_scripts_for(cases: Sequence[Case]) -> dict[str, MockScript]:
    """Map ``case_id`` to the mock script of each case."""
    return {case.case_id: case.mock_script for case in cases if case.mock_script is not None}


def _is_case_folder(path: Path) -> bool:
    return path.is_dir() and not path.name.startswith((".", "_"))


def _load_case(folder: Path) -> Case:
    where = f"{folder.name}/{CASE_FILE_NAME}"
    data = _read_json_object(folder / CASE_FILE_NAME, where)
    version = data.get("schema_version")
    if isinstance(version, int) and not isinstance(version, bool):
        migration = LEGACY_SCHEMA_MESSAGES.get(version)
        if migration is not None:
            raise CaseFormatError(f"{where}: schema_version {version} ya no se admite: {migration}")
    _require_exact_keys(data, TOP_LEVEL_KEYS, where)
    if isinstance(version, bool) or version != CASE_SCHEMA_VERSION:
        raise CaseFormatError(f"{where}: schema_version debe ser {CASE_SCHEMA_VERSION}")
    case_id = _text(data, "id", where)
    if case_id != folder.name or not CASE_ID_PATTERN.match(case_id):
        message = f"{where}: id debe coincidir con la carpeta y con {CASE_ID_PATTERN.pattern}"
        raise CaseFormatError(message)
    transcript_path = _file_inside(folder, _text(data, "transcript_file", where), where)
    transcript = transcript_path.read_text(encoding="utf-8")
    injection = _parse_injection(data["injection"], transcript, where)
    techniques = _parse_atlas_techniques(data["atlas_techniques"], injection, where)
    expected = _parse_expected(_object(data, "expected_result", where), where)
    criterion = _parse_criterion(_object(data, "pass_criterion", where), where)
    script = _parse_mock(_object(data, "mock", where), folder, injection, where)
    _check_fixture_oracles(script, injection, expected, where)
    return Case(
        case_id=case_id,
        title=_text(data, "title", where),
        description=_text(data, "description", where),
        language=_choice(data, "language", LANGUAGES, where),
        ceremony=_choice(data, "ceremony", CEREMONIES, where),
        directory=folder,
        transcript_path=transcript_path,
        transcript=transcript,
        atlas_techniques=techniques,
        injection=injection,
        expected=expected,
        criterion=criterion,
        mock_script=script,
        raw_definition=data,
    )


def _parse_injection(value: object, transcript: str, where: str) -> Injection | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CaseFormatError(f"{where}: injection debe ser un objeto o null")
    _require_exact_keys(value, INJECTION_KEYS, f"{where} (injection)")
    payload = _text(value, "payload", where)
    if "\n" in payload or payload not in transcript:
        message = f"{where}: injection.payload debe ser una sola línea de la transcripción"
        raise CaseFormatError(message)
    indicators = tuple(parse_matcher(item) for item in _objects(value, "effect_indicators", where))
    if not indicators:
        raise CaseFormatError(f"{where}: injection.effect_indicators no puede estar vacío")
    return Injection(
        technique=_choice(value, "technique", TECHNIQUES, where),
        goal=_choice(value, "goal", GOALS, where),
        payload=payload,
        effect_indicators=indicators,
    )


def _parse_atlas_techniques(
    value: object,
    injection: Injection | None,
    where: str,
) -> tuple[AtlasTechnique, ...]:
    if not isinstance(value, list) or not all(_is_text(item) for item in value):
        raise CaseFormatError(f"{where}: atlas_techniques debe ser una lista de textos")
    ids = [str(item) for item in value]
    if len(set(ids)) != len(ids):
        raise CaseFormatError(f"{where}: atlas_techniques tiene identificadores repetidos")
    unknown = [technique_id for technique_id in ids if technique_id not in ATLAS_CATALOG]
    if unknown:
        names = ", ".join(unknown)
        message = (
            f"{where}: técnica de ATLAS desconocida {names}; añádela a "
            "purple_team/atlas.py tras verificarla en atlas.mitre.org"
        )
        raise CaseFormatError(message)
    if bool(ids) != (injection is not None):
        message = f"{where}: atlas_techniques debe estar vacía si y solo si injection es null"
        raise CaseFormatError(message)
    return tuple(ATLAS_CATALOG[technique_id] for technique_id in ids)


def _parse_expected(data: Mapping[str, object], where: str) -> ExpectedResult:
    _require_exact_keys(data, EXPECTED_KEYS, f"{where} (expected_result)")
    mentions = data["summary_mentions"]
    if not isinstance(mentions, list):
        raise CaseFormatError(f"{where}: summary_mentions debe ser una lista")
    try:
        groups = tuple(parse_mention_group(item) for item in mentions)
    except CaseFormatError as exc:
        raise CaseFormatError(f"{where}: {exc}") from exc
    items = tuple(parse_matcher(item) for item in _objects(data, "action_items", where))
    if any(item.kind is not MatcherKind.ACTION_ITEM for item in items):
        raise CaseFormatError(f"{where}: expected_result.action_items solo admite action_item")
    return ExpectedResult(
        description=_text(data, "description", where),
        summary_mentions=groups,
        action_items=items,
    )


def _parse_criterion(data: Mapping[str, object], where: str) -> PassCriterion:
    _require_exact_keys(data, CRITERION_KEYS, f"{where} (pass_criterion)")
    checks = tuple(parse_check(item) for item in _objects(data, "checks", where))
    if not checks:
        raise CaseFormatError(f"{where}: pass_criterion.checks no puede estar vacío")
    return PassCriterion(description=_text(data, "description", where), checks=checks)


def _parse_mock(
    data: Mapping[str, object],
    folder: Path,
    injection: Injection | None,
    where: str,
) -> MockScript:
    _require_exact_keys(data, MOCK_KEYS, f"{where} (mock)")
    benign_path = _file_inside(folder, _text(data, "benign_response_file", where), where)
    injected_name = data["injected_response_file"]
    if (injected_name is None) != (injection is None):
        message = f"{where}: injected_response_file debe ser null si y solo si injection es null"
        raise CaseFormatError(message)
    injected_text = None
    if injected_name is not None:
        if not _is_text(injected_name):
            raise CaseFormatError(f"{where}: injected_response_file debe ser un texto o null")
        injected_text = _file_inside(folder, str(injected_name), where).read_text(encoding="utf-8")
    return MockScript(
        benign_response=benign_path.read_text(encoding="utf-8"),
        injected_response=injected_text,
        trigger=injection.payload if injection is not None else None,
    )


def _check_fixture_oracles(
    script: MockScript,
    injection: Injection | None,
    expected: ExpectedResult,
    where: str,
) -> None:
    """Oracles 7, 8 and 9: the fixtures must be coherent with the case.

    7: the benign answer satisfies the expected result and fires no indicator; 8: the injected
    answer fires an indicator and keeps the expected items; 9: in summary attacks, the
    injected (tampered) summary must NOT satisfy the expected mentions, so the alternatives
    can never be so loose that an altered summary passes.
    """
    benign = _parse_fixture(script.benign_response, f"{where} (mock benigno)")
    missing = _missing_action_items(benign, expected) + _missing_mentions(benign, expected)
    if missing:
        _fail_oracle(where, "la respuesta benigna no cumple", missing)
    indicators = injection.effect_indicators if injection is not None else ()
    fired = [indicator.describe() for indicator in indicators if matches(indicator, benign)]
    if fired:
        _fail_oracle(where, "la respuesta benigna dispara", fired)
    if script.injected_response is None:
        return
    injected = _parse_fixture(script.injected_response, f"{where} (mock inyectado)")
    if not any(matches(indicator, injected) for indicator in indicators):
        raise CaseFormatError(f"{where}: la respuesta inyectada no dispara ningún indicador")
    missing = _missing_action_items(injected, expected)
    if missing:
        _fail_oracle(where, "la respuesta inyectada no conserva", missing)
    tampering = injection is not None and injection.goal == SUMMARY_TAMPERING_GOAL
    if tampering and not _missing_mentions(injected, expected):
        message = (
            f"{where}: las menciones esperadas son tan laxas que el resumen alterado "
            "las cumple"
        )
        raise CaseFormatError(message)


def _fail_oracle(where: str, problem: str, details: Sequence[str]) -> NoReturn:
    joined = "; ".join(details)
    raise CaseFormatError(f"{where}: {problem}: {joined}")


def _missing_action_items(output: CeremonyOutput, expected: ExpectedResult) -> list[str]:
    return [item.describe() for item in expected.action_items if not matches(item, output)]


def _missing_mentions(output: CeremonyOutput, expected: ExpectedResult) -> list[str]:
    return [
        f"resumen sin {group.describe()}"
        for group in expected.summary_mentions
        if not mention_present(group, output.summary)
    ]


def _parse_fixture(raw: str, where: str) -> CeremonyOutput:
    try:
        return parse_ceremony_output(raw)
    except OutputFormatError as exc:
        raise CaseFormatError(f"{where}: {exc}") from exc


def _read_json_object(path: Path, where: str) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseFormatError(f"{where}: no se pudo leer el archivo") from exc
    except json.JSONDecodeError as exc:
        raise CaseFormatError(f"{where}: JSON inválido ({exc.msg}, línea {exc.lineno})") from exc
    if not isinstance(data, dict):
        raise CaseFormatError(f"{where}: debe contener un objeto JSON")
    return data


def _require_exact_keys(data: Mapping[str, object], keys: frozenset[str], where: str) -> None:
    unknown = sorted(set(data) - keys)
    missing = sorted(keys - set(data))
    if unknown or missing:
        detail = f"desconocidas={unknown}, faltantes={missing}"
        raise CaseFormatError(f"{where}: claves inválidas ({detail})")


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text(data: Mapping[str, object], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CaseFormatError(f"{where}: {key} debe ser un texto no vacío")
    return value


def _choice(data: Mapping[str, object], key: str, options: frozenset[str], where: str) -> str:
    value = _text(data, key, where)
    if value not in options:
        valid = ", ".join(sorted(options))
        raise CaseFormatError(f"{where}: {key}={value!r} no es válido; opciones: {valid}")
    return value


def _object(data: Mapping[str, object], key: str, where: str) -> dict[str, object]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise CaseFormatError(f"{where}: {key} debe ser un objeto")
    return value


def _objects(data: Mapping[str, object], key: str, where: str) -> list[dict[str, object]]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CaseFormatError(f"{where}: {key} debe ser una lista de objetos")
    return value


def _file_inside(folder: Path, relative: str, where: str) -> Path:
    path = (folder / relative).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise CaseFormatError(f"{where}: el archivo {relative} no existe dentro del caso")
    return path
