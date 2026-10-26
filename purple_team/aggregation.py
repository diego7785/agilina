"""Aggregated summary of repeated runs: rates per case and per defense mode.

Every rate excludes the runs that ended in error from its denominator (they are counted
apart in ``errors``). ``injection_reached_model_rate`` compares the input scanners only,
``injection_effect_rate`` the whole flow (scanner + model + system policy).
``redacted_legit_lines`` and ``expected_items_*`` measure what the scanner costs.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Self

from purple_team.config import DefenseMode
from purple_team.records import (
    NOT_APPLICABLE,
    TECHNIQUE_SEPARATOR,
    CaseRecord,
    CaseStatus,
    RunRecord,
    atlas_cell,
    format_cell,
)

AGGREGATE_SCHEMA_VERSION: Final = 2
AGGREGATES_DIR_NAME: Final = "aggregates"
RATE_DECIMALS: Final = 3
MEAN_DECIMALS: Final = 2
RUN_ID_SEPARATOR: Final = ";"
AGGREGATE_COLUMNS: Final = (
    "group_id",
    "provider",
    "model",
    "defense",
    "case_id",
    "has_injection",
    "atlas_techniques",
    "runs",
    "completed",
    "errors",
    "injection_effect",
    "injection_effect_rate",
    "passed",
    "pass_rate",
    "injection_reached_model",
    "injection_reached_model_rate",
    "injection_in_model_output",
    "injection_in_model_output_rate",
    "input_detections_mean",
    "blocked_actions_mean",
    "system_policy_blocks",
    "redacted_legit_lines_mean",
    "legit_lines",
    "expected_items_found",
    "expected_items_rate",
    "run_ids",
)


def rate(count: int | None, total: int) -> float | None:
    """``count / total`` rounded to 3 decimals; ``None`` when not applicable or ``total = 0``."""
    if count is None or total == 0:
        return None
    return round(count / total, RATE_DECIMALS)


def mean(total: int, count: int) -> float | None:
    """Mean rounded to 2 decimals; ``None`` when there is nothing to average."""
    if count == 0:
        return None
    return round(total / count, MEAN_DECIMALS)


def _decimal_cell(value: float | None, decimals: int) -> str:
    return NOT_APPLICABLE if value is None else f"{value:.{decimals}f}"


@dataclass(frozen=True, slots=True)
class CaseModeAggregate:
    """One case under one defense mode over its N runs (one row of the CSV)."""

    mode: DefenseMode
    case_id: str
    has_injection: bool
    atlas_techniques: str
    runs: int
    completed: int
    errors: int
    injection_effect: int | None
    passed: int
    injection_reached_model: int | None
    injection_in_model_output: int | None
    input_detections_total: int
    blocked_actions_total: int
    policy_blocks: Mapping[str, int]
    redacted_legit_total: int
    legit_lines: int | None
    expected_items_found: int
    expected_items_total: int
    run_ids: tuple[str, ...]

    @classmethod
    def from_records(
        cls,
        mode: DefenseMode,
        records: Sequence[tuple[str, CaseRecord]],
    ) -> Self:
        """Aggregate the ``(run_id, case record)`` pairs of one case and one mode."""
        first = records[0][1]
        evaluations = [
            record.evaluation for _run_id, record in records if record.evaluation is not None
        ]
        completed = sum(1 for _run_id, record in records if record.status is CaseStatus.COMPLETED)
        has_injection = first.case.injection is not None
        effects = _true_count([result.injection_effect for result in evaluations])
        reached = _true_count([result.injection_reached_model for result in evaluations])
        in_output = _true_count([result.injection_in_model_output for result in evaluations])
        return cls(
            mode=mode,
            case_id=first.case.case_id,
            has_injection=has_injection,
            atlas_techniques=atlas_cell(first.case),
            runs=len(records),
            completed=completed,
            errors=len(records) - completed,
            injection_effect=effects if has_injection else None,
            passed=sum(1 for _run_id, record in records if record.passed),
            injection_reached_model=reached if has_injection else None,
            injection_in_model_output=in_output if has_injection else None,
            input_detections_total=sum(result.input_detections for result in evaluations),
            blocked_actions_total=sum(result.blocked_actions for result in evaluations),
            policy_blocks=dict(
                sorted(
                    Counter(
                        reason
                        for _run_id, record in records
                        for reason in record.policy_block_reasons or ()
                    ).items(),
                ),
            ),
            redacted_legit_total=sum(len(result.redacted_legit_lines) for result in evaluations),
            legit_lines=evaluations[0].legit_lines if evaluations else None,
            expected_items_found=sum(result.expected_items_found for result in evaluations),
            expected_items_total=sum(len(result.expected_action_items) for result in evaluations),
            run_ids=tuple(run_id for run_id, _record in records),
        )

    @property
    def injection_effect_rate(self) -> float | None:
        """Share of completed runs where the injection had an effect."""
        return rate(self.injection_effect, self.completed)

    @property
    def pass_rate(self) -> float | None:
        """Share of completed runs that passed the criterion."""
        return rate(self.passed, self.completed)

    @property
    def injection_reached_model_rate(self) -> float | None:
        """Share of completed runs where the payload got past the input guard."""
        return rate(self.injection_reached_model, self.completed)

    @property
    def injection_in_model_output_rate(self) -> float | None:
        """Share of completed runs where the model output carried the injection."""
        return rate(self.injection_in_model_output, self.completed)

    @property
    def input_detections_mean(self) -> float | None:
        """Mean input detections per completed run."""
        return mean(self.input_detections_total, self.completed)

    @property
    def blocked_actions_mean(self) -> float | None:
        """Mean blocked actions per completed run."""
        return mean(self.blocked_actions_total, self.completed)

    @property
    def redacted_legit_lines_mean(self) -> float | None:
        """Mean legitimate lines redacted by the scanner per completed run."""
        return mean(self.redacted_legit_total, self.completed)

    @property
    def expected_items_rate(self) -> float | None:
        """Expected action items kept over the expected items of the completed runs."""
        return rate(self.expected_items_found, self.expected_items_total)

    def to_dict(self) -> dict[str, object]:
        """Typed JSON view: numbers as numbers and ``null`` instead of ``n/a``."""
        return {
            "defense": self.mode.value,
            "case_id": self.case_id,
            "has_injection": self.has_injection,
            "atlas_techniques": _split(self.atlas_techniques),
            "runs": self.runs,
            "completed": self.completed,
            "errors": self.errors,
            "injection_effect": self.injection_effect,
            "injection_effect_rate": self.injection_effect_rate,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "injection_reached_model": self.injection_reached_model,
            "injection_reached_model_rate": self.injection_reached_model_rate,
            "injection_in_model_output": self.injection_in_model_output,
            "injection_in_model_output_rate": self.injection_in_model_output_rate,
            "input_detections_mean": self.input_detections_mean,
            "blocked_actions_mean": self.blocked_actions_mean,
            "system_policy_blocks": dict(self.policy_blocks),
            "redacted_legit_lines_mean": self.redacted_legit_lines_mean,
            "legit_lines": self.legit_lines,
            "expected_items_found": self.expected_items_found,
            "expected_items_rate": self.expected_items_rate,
            "run_ids": list(self.run_ids),
        }

    def csv_row(self, group_id: str, provider: str, model: str) -> dict[str, str]:
        """CSV row with the formatting rules of ``run_summary.csv``."""
        cells: dict[str, str] = {
            "group_id": group_id,
            "provider": provider,
            "model": model,
            "defense": self.mode.value,
            "case_id": self.case_id,
            "has_injection": format_cell(self.has_injection),
            "atlas_techniques": self.atlas_techniques,
            "runs": format_cell(self.runs),
            "completed": format_cell(self.completed),
            "errors": format_cell(self.errors),
            "injection_effect": format_cell(self.injection_effect),
            "injection_effect_rate": _decimal_cell(self.injection_effect_rate, RATE_DECIMALS),
            "passed": format_cell(self.passed),
            "pass_rate": _decimal_cell(self.pass_rate, RATE_DECIMALS),
            "injection_reached_model": format_cell(self.injection_reached_model),
            "injection_reached_model_rate": _decimal_cell(
                self.injection_reached_model_rate,
                RATE_DECIMALS,
            ),
            "injection_in_model_output": format_cell(self.injection_in_model_output),
            "injection_in_model_output_rate": _decimal_cell(
                self.injection_in_model_output_rate,
                RATE_DECIMALS,
            ),
            "input_detections_mean": _decimal_cell(self.input_detections_mean, MEAN_DECIMALS),
            "blocked_actions_mean": _decimal_cell(self.blocked_actions_mean, MEAN_DECIMALS),
            "system_policy_blocks": RUN_ID_SEPARATOR.join(
                f"{reason}:{count}" for reason, count in self.policy_blocks.items()
            ),
            "redacted_legit_lines_mean": _decimal_cell(
                self.redacted_legit_lines_mean,
                MEAN_DECIMALS,
            ),
            "legit_lines": format_cell(self.legit_lines),
            "expected_items_found": format_cell(self.expected_items_found),
            "expected_items_rate": _decimal_cell(self.expected_items_rate, RATE_DECIMALS),
            "run_ids": RUN_ID_SEPARATOR.join(self.run_ids),
        }
        return {column: cells[column] for column in AGGREGATE_COLUMNS}


@dataclass(frozen=True, slots=True)
class ModeAggregate:
    """Totals of one defense mode over every case and repetition.

    ``injected_case_runs`` counts the completed case runs that carry an injection: it is the
    denominator of the three injection rates; ``case_runs``/``completed`` that of the pass
    rate.
    """

    mode: DefenseMode
    runs: int
    case_runs: int
    completed: int
    errors: int
    injected_case_runs: int
    injection_effect: int
    injection_reached_model: int
    injection_in_model_output: int
    passed: int
    input_detections: int
    blocked_actions: int
    redacted_legit_lines: int
    legit_lines: int
    expected_items_found: int
    expected_items_total: int

    @classmethod
    def from_rows(cls, mode: DefenseMode, rows: Sequence[CaseModeAggregate], runs: int) -> Self:
        """Sum the rows of one mode."""
        injected = [row for row in rows if row.has_injection]
        return cls(
            mode=mode,
            runs=runs,
            case_runs=sum(row.runs for row in rows),
            completed=sum(row.completed for row in rows),
            errors=sum(row.errors for row in rows),
            injected_case_runs=sum(row.completed for row in injected),
            injection_effect=sum(row.injection_effect or 0 for row in injected),
            injection_reached_model=sum(row.injection_reached_model or 0 for row in injected),
            injection_in_model_output=sum(row.injection_in_model_output or 0 for row in injected),
            passed=sum(row.passed for row in rows),
            input_detections=sum(row.input_detections_total for row in rows),
            blocked_actions=sum(row.blocked_actions_total for row in rows),
            redacted_legit_lines=sum(row.redacted_legit_total for row in rows),
            legit_lines=sum((row.legit_lines or 0) * row.completed for row in rows),
            expected_items_found=sum(row.expected_items_found for row in rows),
            expected_items_total=sum(row.expected_items_total for row in rows),
        )

    @property
    def injection_effect_rate(self) -> float | None:
        """Effect over the completed injected case runs."""
        return rate(self.injection_effect, self.injected_case_runs)

    @property
    def injection_reached_model_rate(self) -> float | None:
        """Payloads that got past the input guard over the completed injected case runs."""
        return rate(self.injection_reached_model, self.injected_case_runs)

    @property
    def injection_in_model_output_rate(self) -> float | None:
        """Injected model outputs over the completed injected case runs."""
        return rate(self.injection_in_model_output, self.injected_case_runs)

    @property
    def pass_rate(self) -> float | None:
        """Passed over completed case runs."""
        return rate(self.passed, self.completed)

    @property
    def redacted_legit_rate(self) -> float | None:
        """Redacted legitimate lines over the legitimate lines of the completed case runs."""
        return rate(self.redacted_legit_lines, self.legit_lines)

    @property
    def expected_items_rate(self) -> float | None:
        """Expected action items kept over those of the completed case runs."""
        return rate(self.expected_items_found, self.expected_items_total)

    def to_dict(self) -> dict[str, object]:
        """JSON view."""
        return {
            "runs": self.runs,
            "case_runs": self.case_runs,
            "completed": self.completed,
            "errors": self.errors,
            "injected_case_runs": self.injected_case_runs,
            "injection_effect": self.injection_effect,
            "injection_effect_rate": self.injection_effect_rate,
            "injection_reached_model": self.injection_reached_model,
            "injection_reached_model_rate": self.injection_reached_model_rate,
            "injection_in_model_output": self.injection_in_model_output,
            "injection_in_model_output_rate": self.injection_in_model_output_rate,
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "input_detections": self.input_detections,
            "blocked_actions": self.blocked_actions,
            "redacted_legit_lines": self.redacted_legit_lines,
            "legit_lines": self.legit_lines,
            "redacted_legit_rate": self.redacted_legit_rate,
            "expected_items_found": self.expected_items_found,
            "expected_items_total": self.expected_items_total,
            "expected_items_rate": self.expected_items_rate,
        }


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Aggregated summary of a group of runs (``outputs/aggregates/<group_id>.*``)."""

    group_id: str
    harness_version: str
    provider: str
    model: str
    modes: tuple[DefenseMode, ...]
    repeat: int
    case_ids: tuple[str, ...]
    run_ids: tuple[tuple[DefenseMode, tuple[str, ...]], ...]
    rows: tuple[CaseModeAggregate, ...]
    per_mode: tuple[ModeAggregate, ...]
    requested_modes: tuple[DefenseMode, ...]
    unavailable_modes: Mapping[DefenseMode, str]
    system_policy: object

    def to_dict(self) -> dict[str, object]:
        """JSON view."""
        return {
            "schema_version": AGGREGATE_SCHEMA_VERSION,
            "harness_version": self.harness_version,
            "group_id": self.group_id,
            "provider": self.provider,
            "model": self.model,
            "modes": [mode.value for mode in self.modes],
            "requested_modes": [mode.value for mode in self.requested_modes],
            "unavailable_modes": {
                mode.value: reason for mode, reason in self.unavailable_modes.items()
            },
            "system_policy": self.system_policy,
            "repeat": self.repeat,
            "case_ids": list(self.case_ids),
            "run_ids": {mode.value: list(run_ids) for mode, run_ids in self.run_ids},
            "per_mode": {totals.mode.value: totals.to_dict() for totals in self.per_mode},
            "rows": [row.to_dict() for row in self.rows],
        }

    def csv_rows(self) -> list[dict[str, str]]:
        """One CSV row per (mode, case), in the order of the requested modes."""
        return [row.csv_row(self.group_id, self.provider, self.model) for row in self.rows]


def aggregate_runs(
    group_id: str,
    runs: Sequence[RunRecord],
    repeat: int,
    *,
    unavailable: Mapping[DefenseMode, str],
    requested_modes: Sequence[DefenseMode],
) -> Aggregate:
    """Group the case records of every run by mode (in order of appearance) and by case.

    ``unavailable`` lists the requested modes that could not run, with the reason.
    """
    if not runs:
        raise ValueError("No hay corridas que agregar")
    modes = tuple(dict.fromkeys(run.defense for run in runs))
    case_ids = tuple(sorted({record.case.case_id for run in runs for record in run.cases}))
    rows: list[CaseModeAggregate] = []
    per_mode: list[ModeAggregate] = []
    run_ids: list[tuple[DefenseMode, tuple[str, ...]]] = []
    for mode in modes:
        mode_runs = [run for run in runs if run.defense is mode]
        run_ids.append((mode, tuple(run.run_id for run in mode_runs)))
        mode_rows = [
            CaseModeAggregate.from_records(mode, _records_of(mode_runs, case_id))
            for case_id in case_ids
        ]
        rows.extend(mode_rows)
        per_mode.append(ModeAggregate.from_rows(mode, mode_rows, len(mode_runs)))
    first = runs[0]
    return Aggregate(
        group_id=group_id,
        harness_version=first.harness_version,
        provider=first.provider,
        model=first.model,
        modes=modes,
        repeat=repeat,
        case_ids=case_ids,
        run_ids=tuple(run_ids),
        rows=tuple(rows),
        per_mode=tuple(per_mode),
        requested_modes=tuple(requested_modes),
        unavailable_modes=dict(unavailable),
        # Name, source and effective rules of the system policy (same in every run of a group).
        system_policy=first.config.get("system_policy"),
    )


def _records_of(runs: Sequence[RunRecord], case_id: str) -> list[tuple[str, CaseRecord]]:
    return [
        (run.run_id, record)
        for run in runs
        for record in run.cases
        if record.case.case_id == case_id
    ]


def _true_count(flags: Sequence[bool | None]) -> int:
    """How many flags are ``True`` (``None`` counts as not true)."""
    return sum(1 for flag in flags if flag)


def _split(cell: str) -> list[str]:
    return cell.split(TECHNIQUE_SEPARATOR) if cell else []
