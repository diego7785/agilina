"""Composition root: the only place that chooses concrete implementations.

It reads nothing by itself: the configuration decides the provider (mock, Ollama or cloud)
and the defense mode (``off``, ``own``, ``llm-guard``, ``own-llm-guard``, ``prompt-guard`` or
``own-prompt-guard``); the rest of the code only sees the ports. The model-based detectors
(LLM Guard, Llama Prompt Guard 2) are loaded here, once per process and only when a
requested mode needs them, before any preflight or folder.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, assert_never

from purple_team.aggregation import (
    AGGREGATE_COLUMNS,
    AGGREGATES_DIR_NAME,
    Aggregate,
    aggregate_runs,
)
from purple_team.atlas import ATLAS_DATA_VERSION
from purple_team.cases import Case, load_cases, mock_scripts_for, validate_against_policy
from purple_team.clock import Clock
from purple_team.config import ConfigSource, DefenseMode, HarnessConfig
from purple_team.core.ceremony import CeremonyCloser
from purple_team.core.models import Destination, canonical_target
from purple_team.core.prompts import SystemPrompt, load_system_prompt
from purple_team.defense.input_guard import DEFAULT_REGEX_DETECTOR, InputGuard
from purple_team.defense.layered import LayeredDefense, NoDefense
from purple_team.defense.llm_guard import (
    LlmGuardDetector,
    llm_guard_version,
    load_prompt_injection_scanner,
)
from purple_team.defense.models import Defense, LineDetector
from purple_team.defense.output_guard import OutputGuard
from purple_team.defense.prompt_guard import PromptGuardDetector, load_prompt_guard_classifier
from purple_team.errors import ConfigError, RunExistsError
from purple_team.pipeline import AgentPipeline
from purple_team.policy import DefensePolicy
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

COMPARISONS_DIR_NAME: Final = "comparisons"
COMPARISON_SUFFIX: Final = ".csv"
AGGREGATE_CSV_SUFFIX: Final = ".csv"
AGGREGATE_JSON_SUFFIX: Final = ".json"
COMPARISON_COLUMNS: Final = (
    "case_id",
    "has_injection",
    "effect_off",
    "effect_on",
    "passed_off",
    "passed_on",
    "input_detections_on",
    "blocked_actions_on",
    "run_id_off",
    "run_id_on",
)
LLM_GUARD_MODES: Final = frozenset({DefenseMode.LLM_GUARD, DefenseMode.OWN_LLM_GUARD})
PROMPT_GUARD_MODES: Final = frozenset({DefenseMode.PROMPT_GUARD, DefenseMode.OWN_PROMPT_GUARD})
LLM_GUARD_NAME: Final = "LLM Guard"
PROMPT_GUARD_NAME: Final = "Llama Prompt Guard 2"


@dataclass(frozen=True, slots=True)
class HarnessSetup:
    """Cases, prompt, team context and the policy derived from it, already cross-validated."""

    cases: tuple[Case, ...]
    system_prompt: SystemPrompt
    team_context: TeamContext
    policy: DefensePolicy


@dataclass(frozen=True, slots=True)
class ModelDetectors:
    """Model-based input detectors loaded once per process (``None`` when not requested)."""

    llm_guard: LlmGuardDetector | None
    prompt_guard: PromptGuardDetector | None


NO_MODEL_DETECTORS: Final = ModelDetectors(llm_guard=None, prompt_guard=None)


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """Both runs of ``compare`` and where their records were written."""

    run_off: RunRecord
    run_on: RunRecord
    paths_off: tuple[Path, Path]
    paths_on: tuple[Path, Path]
    csv_path: Path


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    """Every run of a repeated measurement, its records and the aggregated summary."""

    runs: tuple[RunRecord, ...]
    paths: tuple[tuple[Path, Path], ...]
    aggregate: Aggregate
    aggregate_paths: tuple[Path, Path]


def load_validated_setup(config: HarnessConfig, case_ids: Sequence[str]) -> HarnessSetup:
    """Load cases, prompt and team context and check every expected item is reachable."""
    cases = load_cases(config.cases_dir, case_ids)
    system_prompt = load_system_prompt(config.system_prompt_file)
    team_context = load_team_context(config.team_context_file)
    policy = DefensePolicy.from_team_context(team_context, config.max_content_chars)
    validate_against_policy(cases, policy, known_issue_keys(team_context))
    return HarnessSetup(cases, system_prompt, team_context, policy)


def known_issue_keys(team_context: TeamContext) -> frozenset[str]:
    """Canonical keys of the issues listed in the team context (oracle 10)."""
    return frozenset(
        canonical_target(Destination.JIRA_COMMENT, key) for key in team_context.jira_issue_keys
    )


def load_llm_detector(
    config: HarnessConfig,
    modes: Sequence[DefenseMode],
) -> LlmGuardDetector | None:
    """Load LLM Guard once if any requested mode needs it (``DefenseUnavailableError``)."""
    if not LLM_GUARD_MODES.intersection(modes):
        return None
    scanner = load_prompt_injection_scanner(config.llm_guard)
    return LlmGuardDetector(scanner, config.llm_guard, llm_guard_version())


def load_prompt_guard_detector(
    config: HarnessConfig,
    modes: Sequence[DefenseMode],
    environ: Mapping[str, str],
) -> PromptGuardDetector | None:
    """Load Prompt Guard 2 once if any requested mode needs it (``DefenseUnavailableError``)."""
    if not PROMPT_GUARD_MODES.intersection(modes):
        return None
    classifier = load_prompt_guard_classifier(environ)
    return PromptGuardDetector(classifier, config.prompt_guard)


def load_model_detectors(
    config: HarnessConfig,
    modes: Sequence[DefenseMode],
    environ: Mapping[str, str],
) -> ModelDetectors:
    """LLM Guard first, then Prompt Guard 2; either failing stops everything (exit code 4)."""
    return ModelDetectors(
        llm_guard=load_llm_detector(config, modes),
        prompt_guard=load_prompt_guard_detector(config, modes, environ),
    )


def build_defense(
    config: HarnessConfig,
    policy: DefensePolicy,
    detectors: ModelDetectors,
) -> Defense:
    """``NoDefense`` for ``off``; otherwise the chosen input detectors + the output policy."""
    chosen: tuple[LineDetector, ...]
    match config.defense:
        case DefenseMode.OFF:
            return NoDefense()
        case DefenseMode.OWN:
            chosen = (DEFAULT_REGEX_DETECTOR,)
        case DefenseMode.LLM_GUARD:
            chosen = (_required(detectors.llm_guard, LLM_GUARD_NAME),)
        case DefenseMode.OWN_LLM_GUARD:
            chosen = (DEFAULT_REGEX_DETECTOR, _required(detectors.llm_guard, LLM_GUARD_NAME))
        case DefenseMode.PROMPT_GUARD:
            chosen = (_required(detectors.prompt_guard, PROMPT_GUARD_NAME),)
        case DefenseMode.OWN_PROMPT_GUARD:
            chosen = (
                DEFAULT_REGEX_DETECTOR,
                _required(detectors.prompt_guard, PROMPT_GUARD_NAME),
            )
        case _:
            assert_never(config.defense)
    return LayeredDefense(config.defense, InputGuard(chosen), OutputGuard(policy))


def build_tools() -> ToolDispatcher:
    """Simulated Jira comments, calendar events and Slack messages (the model's proposals)."""
    return ToolDispatcher([SimulatedJiraComment(), SimulatedCalendar(), SimulatedSlack()])


def build_runner(
    config: HarnessConfig,
    *,
    clock: Clock,
    run_id: str | None,
    label: str | None,
    case_ids: Sequence[str],
    environ: Mapping[str, str],
) -> HarnessRunner:
    """Wire provider, defense, tools, cases and recorder for one run."""
    started_at = clock.now()
    if run_id:
        chosen_id = validate_run_id(run_id)
    else:
        chosen_id = make_run_id(started_at, config.provider, config.defense, label)
    setup = load_validated_setup(config, case_ids)
    detectors = load_model_detectors(config, (config.defense,), environ)
    return _assemble(
        config,
        setup=setup,
        detectors=detectors,
        clock=clock,
        run_id=chosen_id,
        started_at=started_at,
        repetition=None,
        environ=environ,
    )


def run_comparison(
    config: HarnessConfig,
    *,
    clock: Clock,
    label: str | None,
    case_ids: Sequence[str],
    environ: Mapping[str, str],
) -> ComparisonResult:
    """Run the same cases with defense off and own (same ``started_at``) and write a CSV.

    Both run folders and the comparison CSV are checked before anything is executed.
    """
    started_at = clock.now()
    setup = load_validated_setup(config, case_ids)
    runner_off, runner_on = (
        _assemble(
            config.with_defense(mode, ConfigSource.CLI),
            setup=setup,
            detectors=NO_MODEL_DETECTORS,
            clock=clock,
            run_id=make_run_id(started_at, config.provider, mode, label),
            started_at=started_at,
            repetition=None,
            environ=environ,
        )
        for mode in (DefenseMode.OFF, DefenseMode.OWN)
    )
    csv_path = comparison_csv_path(config, started_at, label)
    runner_off.preflight()
    runner_on.preflight()
    if csv_path.exists():
        shown = config.display(csv_path)
        raise RunExistsError(f"La comparación {shown} ya existe; elige otro --label")
    run_off = runner_off.run()
    run_on = runner_on.run()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_csv(csv_path, comparison_rows(run_off, run_on), COMPARISON_COLUMNS)
    return ComparisonResult(
        run_off=run_off,
        run_on=run_on,
        paths_off=runner_off.record_paths,
        paths_on=runner_on.record_paths,
        csv_path=csv_path,
    )


def run_measurement(
    config: HarnessConfig,
    *,
    modes: Sequence[DefenseMode],
    repeat: int,
    clock: Clock,
    run_id: str | None,
    label: str | None,
    case_ids: Sequence[str],
    environ: Mapping[str, str],
) -> MeasurementResult:
    """Run every mode ``repeat`` times, interleaved (r01: off, own...; r02: ...), and aggregate.

    Every run and both aggregate files are checked before the first run starts; every run
    records its own real ``started_at`` while the ids share the stamp of the group.
    """
    if run_id and len(modes) > 1:
        raise ConfigError("--run-id solo se admite con una única defensa; usa --label")
    started_at = clock.now()
    group_id = validate_run_id(run_id) if run_id else group_name(config, started_at, label)
    setup = load_validated_setup(config, case_ids)
    detectors = load_model_detectors(config, modes, environ)
    runners = []
    for index in range(1, repeat + 1):
        repetition = Repetition(group_id=group_id, index=index, count=repeat)
        for mode in modes:
            base_id = run_id or make_run_id(started_at, config.provider, mode, label)
            chosen_id = repeated_run_id(base_id, index) if repeat > 1 else base_id
            runner = _assemble(
                config.with_defense(mode, ConfigSource.CLI),
                setup=setup,
                detectors=detectors,
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
    aggregate = aggregate_runs(group_id, runs, repeat)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_summary_csv(csv_path, aggregate.csv_rows(), AGGREGATE_COLUMNS)
    write_json(json_path, aggregate.to_dict())
    return MeasurementResult(
        runs=runs,
        paths=tuple(runner.record_paths for runner in runners),
        aggregate=aggregate,
        aggregate_paths=(csv_path, json_path),
    )


def group_name(config: HarnessConfig, started_at: datetime, label: str | None) -> str:
    """``<stamp>_<provider>[_<label>]``: name of a comparison CSV or of an aggregate."""
    name = f"{format_run_stamp(started_at)}_{config.provider.value}"
    if label:
        name = f"{name}_{normalize_label(label)}"
    return validate_run_id(name)


def comparison_csv_path(config: HarnessConfig, started_at: datetime, label: str | None) -> Path:
    """``outputs/comparisons/<stamp>_<provider>[_<label>].csv``."""
    name = group_name(config, started_at, label)
    return config.outputs_dir / COMPARISONS_DIR_NAME / f"{name}{COMPARISON_SUFFIX}"


def aggregate_paths(config: HarnessConfig, group_id: str) -> tuple[Path, Path]:
    """``outputs/aggregates/<group_id>.csv`` and ``.json``."""
    folder = config.outputs_dir / AGGREGATES_DIR_NAME
    return (
        folder / f"{group_id}{AGGREGATE_CSV_SUFFIX}",
        folder / f"{group_id}{AGGREGATE_JSON_SUFFIX}",
    )


def comparison_rows(run_off: RunRecord, run_on: RunRecord) -> list[dict[str, str]]:
    """One row per case with the effect and the verdict of both runs."""
    rows = []
    for record_off, record_on in zip(run_off.cases, run_on.cases, strict=True):
        evaluation_off = record_off.evaluation
        evaluation_on = record_on.evaluation
        cells: dict[str, object] = {
            "case_id": record_off.case.case_id,
            "has_injection": record_off.case.injection is not None,
            "effect_off": evaluation_off.injection_effect if evaluation_off else None,
            "effect_on": evaluation_on.injection_effect if evaluation_on else None,
            "passed_off": record_off.passed,
            "passed_on": record_on.passed,
            "input_detections_on": evaluation_on.input_detections if evaluation_on else None,
            "blocked_actions_on": evaluation_on.blocked_actions if evaluation_on else None,
            "run_id_off": run_off.run_id,
            "run_id_on": run_on.run_id,
        }
        rows.append({key: format_cell(value) for key, value in cells.items()})
    return rows


def context_record(
    setup: HarnessSetup,
    config: HarnessConfig,
    defense: Defense,
) -> dict[str, object]:
    """Team context, effective policy, defense setup and ATLAS version for the records."""
    return {
        "team_context": setup.team_context.to_record(config.display),
        "effective_policy": setup.policy.to_record(),
        "defense_setup": defense.describe(),
        "atlas_version": ATLAS_DATA_VERSION,
    }


def _required[D: LineDetector](detector: D | None, name: str) -> D:
    if detector is None:
        raise ConfigError(f"El modo de defensa pide {name}, pero no se cargó su detector")
    return detector


def _assemble(
    config: HarnessConfig,
    *,
    setup: HarnessSetup,
    detectors: ModelDetectors,
    clock: Clock,
    run_id: str,
    started_at: datetime | None,
    repetition: Repetition | None,
    environ: Mapping[str, str],
) -> HarnessRunner:
    provider = build_provider(config, mock_scripts=mock_scripts_for(setup.cases), environ=environ)
    closer = CeremonyCloser(provider, config.temperature, setup.team_context)
    defense = build_defense(config, setup.policy, detectors)
    system_outputs = SystemOutputs(setup.team_context)
    pipeline = AgentPipeline(closer, defense, build_tools(), system_outputs)
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
