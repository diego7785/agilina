"""Composition root: the only place that chooses concrete implementations.

It reads nothing by itself: the configuration decides the provider (mock, Ollama or cloud)
and the defense mode (``off``, ``llm-guard-default``, ``llm-guard-tuned`` or
``prompt-guard-2``); the rest of the code only sees the ports. The LLM Guard scanners are
loaded here, once per process and mode, before any preflight or folder; a mode whose model
cannot load is reported and skipped. The system policy is wired in every mode.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from purple_team import HARNESS_VERSION
from purple_team.aggregation import (
    AGGREGATE_COLUMNS,
    AGGREGATES_DIR_NAME,
    Aggregate,
    aggregate_runs,
)
from purple_team.atlas import ATLAS_DATA_VERSION
from purple_team.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    CSV_COLUMNS,
    FP_LIMIT_PERCENT,
    GRID_MATCH_TYPES,
    GRID_MODELS,
    GRID_STRIP_SPEAKER,
    GRID_THRESHOLDS,
    MODE_OF_MODEL,
    SELECTION_RULE,
    CalibrationRow,
    CalibrationSet,
    Selection,
    evaluate_row,
    find_overlaps,
    load_calibration_set,
    row_order,
    select_configuration,
)
from purple_team.cases import Case, load_cases, mock_scripts_for, validate_against_policy
from purple_team.clock import Clock, format_utc
from purple_team.config import (
    ConfigSource,
    DefenseMode,
    HarnessConfig,
    ScannerModel,
    ScannerSettings,
)
from purple_team.core.ceremony import CeremonyCloser
from purple_team.core.models import Destination, canonical_target
from purple_team.core.prompts import SystemPrompt, load_system_prompt
from purple_team.defense.input_guard import InputGuard
from purple_team.defense.layered import InputGuardDefense, NoDefense
from purple_team.defense.llm_guard import (
    REVISIONS,
    LlmGuardDetector,
    llm_guard_version,
    load_prompt_injection_scanner,
)
from purple_team.defense.models import Defense, LineDetector
from purple_team.errors import ConfigError, DefenseUnavailableError, RunExistsError
from purple_team.pipeline import AgentPipeline
from purple_team.policy import SystemPolicy
from purple_team.providers.factory import build_provider
from purple_team.recording import RunRecorder, write_json, write_summary_csv
from purple_team.records import Repetition, RunRecord, format_cell
from purple_team.runner import (
    HarnessRunner,
    format_run_stamp,
    make_run_id,
    normalize_label,
    repeated_run_id,
    validate_run_id,
)
from purple_team.team_context import TeamContext, load_team_context
from purple_team.tools.simulated import (
    SimulatedCalendar,
    SimulatedJiraComment,
    SimulatedSlack,
    ToolDispatcher,
)
from purple_team.tools.system_outputs import SystemOutputs

AGGREGATE_CSV_SUFFIX: Final = ".csv"
AGGREGATE_JSON_SUFFIX: Final = ".json"
CALIBRATION_DIR_NAME: Final = "calibration"
CALIBRATION_NAME: Final = "calibration"
RUN_ID_WITH_SEVERAL_MODES: Final = "--run-id solo se admite con una única defensa; usa --label"


@dataclass(frozen=True, slots=True)
class HarnessSetup:
    """Cases, prompt, team context and the system policy derived from it, cross-validated."""

    cases: tuple[Case, ...]
    system_prompt: SystemPrompt
    team_context: TeamContext
    policy: SystemPolicy


@dataclass(frozen=True, slots=True)
class ScannerAvailability:
    """Detectors loaded for the requested scanner modes and the modes that could not load."""

    detectors: Mapping[DefenseMode, LineDetector]
    unavailable: Mapping[DefenseMode, str]

    def runnable(self, modes: Sequence[DefenseMode]) -> tuple[DefenseMode, ...]:
        """Requested modes that can run, in order (``off`` always can)."""
        return tuple(mode for mode in modes if mode not in self.unavailable)


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    """Every run of a repeated measurement, its records and the aggregated summary."""

    runs: tuple[RunRecord, ...]
    paths: tuple[tuple[Path, Path], ...]
    aggregate: Aggregate
    aggregate_paths: tuple[Path, Path]


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Rows, selections and output files of one ``calibrate`` execution."""

    calibration_id: str
    calibration_set: CalibrationSet
    rows: tuple[CalibrationRow, ...]
    selections: tuple[Selection, ...]
    unavailable_models: Mapping[ScannerModel, str]
    paths: tuple[Path, Path]


def load_validated_setup(config: HarnessConfig, case_ids: Sequence[str]) -> HarnessSetup:
    """Load cases, prompt and team context and check every expected item is reachable."""
    cases = load_cases(config.cases_dir, case_ids)
    system_prompt = load_system_prompt(config.system_prompt_file)
    team_context = load_team_context(config.team_context_file)
    policy = SystemPolicy.from_team_context(team_context, config.max_content_chars)
    validate_against_policy(cases, policy, known_issue_keys(team_context))
    return HarnessSetup(cases, system_prompt, team_context, policy)


def known_issue_keys(team_context: TeamContext) -> frozenset[str]:
    """Canonical keys of the issues listed in the team context (oracle 10)."""
    return frozenset(
        canonical_target(Destination.JIRA_COMMENT, key) for key in team_context.jira_issue_keys
    )


def load_scanners(
    config: HarnessConfig,
    modes: Sequence[DefenseMode],
    environ: Mapping[str, str],
) -> ScannerAvailability:
    """Load the scanner of every requested scanner mode, once, in order.

    A mode whose scanner cannot load (``DefenseUnavailableError``) is recorded with its
    message and the next mode is tried.
    """
    detectors: dict[DefenseMode, LineDetector] = {}
    unavailable: dict[DefenseMode, str] = {}
    for mode in modes:
        settings = config.scanner_settings(mode)
        if settings is None:
            continue
        try:
            scanner = load_prompt_injection_scanner(settings, environ)
        except DefenseUnavailableError as exc:
            unavailable[mode] = str(exc)
            continue
        detectors[mode] = LlmGuardDetector(scanner, settings, llm_guard_version())
    return ScannerAvailability(detectors=detectors, unavailable=unavailable)


def build_defense(config: HarnessConfig, detectors: Mapping[DefenseMode, LineDetector]) -> Defense:
    """``NoDefense`` for ``off``; otherwise the input guard with the detector of the mode."""
    if config.defense is DefenseMode.OFF:
        return NoDefense()
    detector = detectors.get(config.defense)
    if detector is None:
        message = f"El modo {config.defense.value} pide un escáner, pero no se cargó su detector"
        raise ConfigError(message)
    return InputGuardDefense(config.defense, InputGuard((detector,)))


def build_tools() -> ToolDispatcher:
    """Simulated Jira comments, calendar events and Slack messages (the model's proposals)."""
    return ToolDispatcher([SimulatedJiraComment(), SimulatedCalendar(), SimulatedSlack()])


def build_runner(
    config: HarnessConfig,
    *,
    scanners: ScannerAvailability,
    clock: Clock,
    run_id: str | None,
    label: str | None,
    case_ids: Sequence[str],
    environ: Mapping[str, str],
) -> HarnessRunner:
    """Wire provider, defense, policy, tools, cases and recorder for one run.

    ``DefenseUnavailableError`` when the scanner of the mode could not load.
    """
    unavailable = scanners.unavailable.get(config.defense)
    if unavailable is not None:
        raise DefenseUnavailableError(unavailable)
    started_at = clock.now()
    if run_id:
        chosen_id = validate_run_id(run_id)
    else:
        chosen_id = make_run_id(started_at, config.provider, config.defense, label)
    setup = load_validated_setup(config, case_ids)
    return _assemble(
        config,
        setup=setup,
        detectors=scanners.detectors,
        clock=clock,
        run_id=chosen_id,
        started_at=started_at,
        repetition=None,
        environ=environ,
    )


def run_measurement(
    config: HarnessConfig,
    *,
    modes: Sequence[DefenseMode],
    scanners: ScannerAvailability,
    repeat: int,
    clock: Clock,
    run_id: str | None,
    label: str | None,
    case_ids: Sequence[str],
    environ: Mapping[str, str],
) -> MeasurementResult:
    """Run every available mode ``repeat`` times, interleaved, and aggregate.

    The modes that ``scanners`` reports as unavailable are skipped and recorded in the
    aggregate. Every run and both aggregate files are checked before the first run starts;
    every run records its own real ``started_at`` while the ids share the stamp of the group.
    """
    if run_id and len(modes) > 1:
        raise ConfigError(RUN_ID_WITH_SEVERAL_MODES)
    runnable = scanners.runnable(modes)
    if not runnable:
        raise DefenseUnavailableError("ningún modo pedido está disponible; no se ejecutó nada")
    started_at = clock.now()
    group_id = validate_run_id(run_id) if run_id else group_name(config, started_at, label)
    setup = load_validated_setup(config, case_ids)
    runners = []
    for index in range(1, repeat + 1):
        repetition = Repetition(group_id=group_id, index=index, count=repeat)
        for mode in runnable:
            base_id = run_id or make_run_id(started_at, config.provider, mode, label)
            chosen_id = repeated_run_id(base_id, index) if repeat > 1 else base_id
            runner = _assemble(
                config.with_defense(mode, ConfigSource.CLI),
                setup=setup,
                detectors=scanners.detectors,
                clock=clock,
                run_id=chosen_id,
                started_at=None,
                repetition=repetition,
                environ=environ,
            )
            runners.append(runner)
    csv_path, json_path = aggregate_paths(config, group_id)
    for runner in runners:
        runner.preflight()
    for path in (csv_path, json_path):
        if path.exists():
            shown = config.display(path)
            raise RunExistsError(f"El agregado {shown} ya existe; elige otro --label o --run-id")
    runs = tuple(runner.run() for runner in runners)
    unavailable = {mode: scanners.unavailable[mode] for mode in modes if mode not in runnable}
    aggregate = aggregate_runs(
        group_id,
        runs,
        repeat,
        unavailable=unavailable,
        requested_modes=modes,
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_csv(csv_path, aggregate.csv_rows(), AGGREGATE_COLUMNS)
    write_json(json_path, aggregate.to_dict())
    return MeasurementResult(
        runs=runs,
        paths=tuple(runner.record_paths for runner in runners),
        aggregate=aggregate,
        aggregate_paths=(csv_path, json_path),
    )


def run_calibration(
    config: HarnessConfig,
    *,
    clock: Clock,
    label: str | None,
    environ: Mapping[str, str],
) -> CalibrationResult:
    """Measure the grid of ``calibration.py`` and choose the settings of each mode.

    Nothing is loaded before the output names are free and the calibration lines are proven
    not to overlap the cases. ``DefenseUnavailableError`` (nothing written) when no model
    could load; a model that cannot load is skipped and reported.
    """
    started_at = clock.now()
    calibration_id = f"{format_run_stamp(started_at)}_{CALIBRATION_NAME}"
    if label:
        calibration_id = f"{calibration_id}_{normalize_label(label)}"
    calibration_id = validate_run_id(calibration_id)
    paths = calibration_paths(config, calibration_id)
    for path in paths:
        if path.exists():
            shown = config.display(path)
            raise RunExistsError(f"La calibración {shown} ya existe; elige otro --label")
    calibration_set = load_calibration_set(config.calibration_dir)
    cases = load_cases(config.cases_dir)
    overlaps = find_overlaps(calibration_set, cases)
    if overlaps:
        shown = "; ".join(overlaps)
        raise ConfigError(f"Hay líneas de calibración que solapan con los casos: {shown}")
    rows, unavailable = _measure_grid(calibration_set, environ)
    if not rows:
        reasons = "\n".join(f"{model.value}: {reason}" for model, reason in unavailable.items())
        raise DefenseUnavailableError(f"Ningún modelo de la calibración pudo cargarse.\n{reasons}")
    selections = tuple(
        select_configuration(MODE_OF_MODEL[model], model_rows)
        for model in GRID_MODELS
        if (model_rows := [row for row in rows if row.settings.model is model])
    )
    result = CalibrationResult(
        calibration_id=calibration_id,
        calibration_set=calibration_set,
        rows=tuple(sorted(rows, key=row_order)),
        selections=selections,
        unavailable_models=unavailable,
        paths=paths,
    )
    record = calibration_record(
        config,
        result,
        cases=cases,
        started_at=format_utc(started_at),
        finished_at=format_utc(clock.now()),
    )
    csv_path, json_path = paths
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_csv(csv_path, calibration_csv_rows(result), CSV_COLUMNS)
    write_json(json_path, record)
    return result


def _measure_grid(
    calibration_set: CalibrationSet,
    environ: Mapping[str, str],
) -> tuple[list[CalibrationRow], dict[ScannerModel, str]]:
    """One scanner load per (model, match_type, threshold); both speaker options share it."""
    rows: list[CalibrationRow] = []
    unavailable: dict[ScannerModel, str] = {}
    version = llm_guard_version()
    for model in GRID_MODELS:
        for match_type in GRID_MATCH_TYPES:
            for threshold in GRID_THRESHOLDS:
                if model in unavailable:
                    break
                loaded = ScannerSettings(model, threshold, match_type, strip_speaker=True)
                try:
                    scanner = load_prompt_injection_scanner(loaded, environ)
                except DefenseUnavailableError as exc:
                    unavailable[model] = str(exc)
                    break
                for strip_speaker in GRID_STRIP_SPEAKER:
                    settings = ScannerSettings(model, threshold, match_type, strip_speaker)
                    detector = LlmGuardDetector(scanner, settings, version)
                    rows.append(evaluate_row(detector, settings, REVISIONS[model], calibration_set))
                # One model at a time in memory (64 loads of 0.7-1.1 GB each).
                del scanner, detector
    return rows, unavailable


def calibration_paths(config: HarnessConfig, calibration_id: str) -> tuple[Path, Path]:
    """``outputs/calibration/<calibration_id>.csv`` and ``.json``."""
    folder = config.outputs_dir / CALIBRATION_DIR_NAME
    return (
        folder / f"{calibration_id}{AGGREGATE_CSV_SUFFIX}",
        folder / f"{calibration_id}{AGGREGATE_JSON_SUFFIX}",
    )


def calibration_csv_rows(result: CalibrationResult) -> list[dict[str, str]]:
    """One CSV row per configuration (``true``/``false`` as in the run summaries)."""
    selected = {id(selection.row) for selection in result.selections}
    return [
        {
            key: format_cell(value)
            for key, value in row.cells(result.calibration_id, selected=id(row) in selected).items()
        }
        for row in result.rows
    ]


def configured_settings(config: HarnessConfig, mode: DefenseMode) -> ScannerSettings:
    """Settings of a calibrated mode in the configuration in use (to compare the selection)."""
    settings = config.scanner_settings(mode)
    if settings is None:
        raise ValueError(f"{mode.value} no tiene escáner")
    return settings


def selection_matches(config: HarnessConfig, selection: Selection) -> bool:
    """Whether the configuration in use already has the three values chosen by ``calibrate``."""
    return configured_settings(config, selection.mode) == selection.row.settings


def calibration_record(
    config: HarnessConfig,
    result: CalibrationResult,
    *,
    cases: Sequence[Case],
    started_at: str,
    finished_at: str,
) -> dict[str, object]:
    """Complete JSON of a calibration (handoff/24 section 3.7)."""
    files = {
        name: {
            "path": config.display(part.path),
            "sha256": part.sha256,
            "items": len(part.items),
        }
        for name, part in (
            ("legitimate", result.calibration_set.legitimate),
            ("injections", result.calibration_set.injections),
        )
    }
    selected = {id(selection.row) for selection in result.selections}
    rows = [
        {
            **row.cells(result.calibration_id, selected=id(row) in selected),
            "false_positive_ids": list(row.false_positive_ids),
            "detected_ids": list(row.detected_ids),
            "missed_ids": list(row.missed_ids),
        }
        for row in result.rows
    ]
    comparison = {
        selection.mode.value: {
            "configured": configured_settings(config, selection.mode).to_record(),
            "matches": selection_matches(config, selection),
        }
        for selection in result.selections
    }
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "calibration_id": result.calibration_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "llm_guard_version": llm_guard_version(),
        "config_file": config.display(config.config_file),
        "files": files,
        "overlap_check": {
            "cases_dir": config.display(config.cases_dir),
            "cases": len(cases),
            "overlaps": [],
        },
        "grid": {
            "models": [model.value for model in GRID_MODELS],
            "match_types": [match_type.value for match_type in GRID_MATCH_TYPES],
            "strip_speaker": list(GRID_STRIP_SPEAKER),
            "thresholds": list(GRID_THRESHOLDS),
        },
        "fp_limit": FP_LIMIT_PERCENT / 100,
        "selection_rule": SELECTION_RULE,
        "unavailable_models": {
            model.value: reason for model, reason in result.unavailable_models.items()
        },
        "selection": {selection.mode.value: selection.to_dict() for selection in result.selections},
        "config_comparison": comparison,
        "rows": rows,
    }


def group_name(config: HarnessConfig, started_at: datetime, label: str | None) -> str:
    """``<stamp>_<provider>[_<label>]``: name of an aggregate."""
    name = f"{format_run_stamp(started_at)}_{config.provider.value}"
    if label:
        name = f"{name}_{normalize_label(label)}"
    return validate_run_id(name)


def aggregate_paths(config: HarnessConfig, group_id: str) -> tuple[Path, Path]:
    """``outputs/aggregates/<group_id>.csv`` and ``.json``."""
    folder = config.outputs_dir / AGGREGATES_DIR_NAME
    return (
        folder / f"{group_id}{AGGREGATE_CSV_SUFFIX}",
        folder / f"{group_id}{AGGREGATE_JSON_SUFFIX}",
    )


def context_record(
    setup: HarnessSetup,
    config: HarnessConfig,
    defense: Defense,
) -> dict[str, object]:
    """Team context, system policy, defense setup and ATLAS version for the records."""
    return {
        "team_context": setup.team_context.to_record(config.display),
        "system_policy": setup.policy.to_record(),
        "defense_setup": defense.describe(),
        "atlas_version": ATLAS_DATA_VERSION,
    }


def _assemble(
    config: HarnessConfig,
    *,
    setup: HarnessSetup,
    detectors: Mapping[DefenseMode, LineDetector],
    clock: Clock,
    run_id: str,
    started_at: datetime | None,
    repetition: Repetition | None,
    environ: Mapping[str, str],
) -> HarnessRunner:
    provider = build_provider(config, mock_scripts=mock_scripts_for(setup.cases), environ=environ)
    closer = CeremonyCloser(provider, config.temperature, setup.team_context)
    defense = build_defense(config, detectors)
    system_outputs = SystemOutputs(setup.team_context)
    pipeline = AgentPipeline(closer, defense, setup.policy, build_tools(), system_outputs)
    recorder = RunRecorder(
        run_id=run_id,
        inputs_root=config.inputs_dir,
        outputs_root=config.outputs_dir,
        base_dir=config.base_dir,
    )
    return HarnessRunner(
        config=config,
        provider=provider,
        pipeline=pipeline,
        cases=setup.cases,
        system_prompt=setup.system_prompt,
        recorder=recorder,
        clock=clock,
        run_id=run_id,
        started_at=started_at,
        context_record=context_record(setup, config, defense),
        repetition=repetition,
    )
