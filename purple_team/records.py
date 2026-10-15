"""Values of the run records: ``run_log.json`` (complete) and ``run_summary.csv`` (index)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Self

from purple_team.cases import Case
from purple_team.config import DefenseMode
from purple_team.core.text import sha256_hex
from purple_team.evaluation.evaluator import Evaluation
from purple_team.pipeline import PipelineTrace

RECORD_SCHEMA_VERSION: Final = 3
NOT_APPLICABLE: Final = "n/a"
TRUE_CELL: Final = "true"
FALSE_CELL: Final = "false"
CHECK_SEPARATOR: Final = ";"
TECHNIQUE_SEPARATOR: Final = ";"
SUMMARY_COLUMNS: Final = (
    "run_id",
    "started_at",
    "provider",
    "model",
    "defense",
    "case_id",
    "title",
    "status",
    "has_injection",
    "technique",
    "goal",
    "atlas_techniques",
    "input_detections",
    "injection_reached_model",
    "injection_in_model_output",
    "injection_effect",
    "output_valid",
    "blocked_actions",
    "tool_calls",
    "system_outputs",
    "passed",
    "failed_checks",
    "inputs_dir",
    "outputs_dir",
)
EVALUATION_COLUMNS: Final = (
    "input_detections",
    "injection_reached_model",
    "injection_in_model_output",
    "injection_effect",
    "blocked_actions",
    "failed_checks",
)


class CaseStatus(StrEnum):
    """Whether the case ran to the end or an expected error stopped it."""

    COMPLETED = "completed"
    ERROR = "error"


def atlas_cell(case: Case) -> str:
    """ATLAS ids of a case separated by ``;`` (empty for controls)."""
    return TECHNIQUE_SEPARATOR.join(technique.technique_id for technique in case.atlas_techniques)


def format_cell(value: object) -> str:
    """CSV cell: booleans as ``true``/``false`` and missing values as ``n/a``."""
    if value is None:
        return NOT_APPLICABLE
    if isinstance(value, bool):
        return TRUE_CELL if value else FALSE_CELL
    return str(value)


@dataclass(frozen=True, slots=True)
class CaseRecord:
    """One entry of ``cases`` in the run log; paths are already displayed (section 7.3)."""

    case: Case
    status: CaseStatus
    timestamp: str
    inputs_path: str
    outputs_path: str
    transcript_file: str
    trace: PipelineTrace | None
    evaluation: Evaluation | None
    error: str | None

    @property
    def passed(self) -> bool:
        """A case passes only if it completed and every check passed."""
        return self.evaluation is not None and self.evaluation.passed

    def to_dict(self) -> dict[str, object]:
        """JSON view (plan section 8.1)."""
        injection = self.case.injection
        trace = self.trace
        output_screening = trace.output_screening if trace is not None else None
        final_output = trace.final_output if trace is not None else None
        return {
            "case_id": self.case.case_id,
            "title": self.case.title,
            "status": self.status.value,
            "error": self.error,
            "has_injection": injection is not None,
            "technique": injection.technique if injection is not None else None,
            "goal": injection.goal if injection is not None else None,
            "atlas_techniques": [technique.to_dict() for technique in self.case.atlas_techniques],
            "timestamp": self.timestamp,
            "paths": {"inputs": self.inputs_path, "outputs": self.outputs_path},
            "input": self._input_dict(),
            "model_output": self._model_output_dict(),
            "output_guard": output_screening.to_dict() if output_screening is not None else None,
            "final_output": final_output.to_dict() if final_output is not None else None,
            "tool_calls": [call.to_dict() for call in trace.tool_calls] if trace else [],
            "system_outputs": [out.to_dict() for out in trace.system_outputs] if trace else [],
            "evaluation": self.evaluation.to_dict() if self.evaluation is not None else None,
        }

    def _input_dict(self) -> dict[str, object]:
        screening = self.trace.input_screening if self.trace is not None else None
        user_content = self.trace.closing.request.user_content if self.trace else None
        return {
            "transcript_file": self.transcript_file,
            "transcript_sha256": sha256_hex(self.case.transcript),
            "transcript": self.case.transcript,
            "model_user_content": user_content,
            "input_guard": screening.to_dict() if screening is not None else None,
        }

    def _model_output_dict(self) -> dict[str, object] | None:
        if self.trace is None:
            return None
        closing = self.trace.closing
        return {
            "provider": closing.response.provider,
            "model": closing.response.model,
            "raw": closing.response.text,
            "thinking": closing.response.thinking,
            "valid": closing.output is not None,
            "parse_error": closing.parse_error,
            "parsed": closing.output.to_dict() if closing.output is not None else None,
        }

    def summary_row(self, run_cells: Mapping[str, str]) -> dict[str, str]:
        """CSV row of the case; ``run_cells`` holds the run-level columns."""
        injection = self.case.injection
        trace = self.trace
        case_cells: dict[str, object] = {
            "case_id": self.case.case_id,
            "title": self.case.title,
            "status": self.status.value,
            "has_injection": injection is not None,
            "technique": injection.technique if injection is not None else None,
            "goal": injection.goal if injection is not None else None,
            "atlas_techniques": atlas_cell(self.case),
            **self._evaluation_cells(),
            "output_valid": trace.closing.output is not None if trace is not None else None,
            "tool_calls": len(trace.tool_calls) if trace is not None else None,
            "system_outputs": len(trace.system_outputs) if trace is not None else None,
            "passed": self.passed,
            "inputs_dir": self.inputs_path,
            "outputs_dir": self.outputs_path,
        }
        cells = {**run_cells, **{key: format_cell(value) for key, value in case_cells.items()}}
        return {column: cells[column] for column in SUMMARY_COLUMNS}

    def _evaluation_cells(self) -> dict[str, object]:
        evaluation = self.evaluation
        if evaluation is None:
            return dict.fromkeys(EVALUATION_COLUMNS)
        return {
            "input_detections": evaluation.input_detections,
            "injection_reached_model": evaluation.injection_reached_model,
            "injection_in_model_output": evaluation.injection_in_model_output,
            "injection_effect": evaluation.injection_effect,
            "blocked_actions": evaluation.blocked_actions,
            "failed_checks": CHECK_SEPARATOR.join(evaluation.failed_checks),
        }


@dataclass(frozen=True, slots=True)
class RunTotals:
    """``totals`` block of the run log."""

    cases: int
    completed: int
    errors: int
    passed: int
    failed: int
    with_injection: int
    injection_reached_model: int
    injection_in_model_output: int
    injection_effect: int
    input_detections: int
    blocked_actions: int

    @classmethod
    def from_cases(cls, records: Sequence[CaseRecord]) -> Self:
        """Aggregate the case records; ``failed`` counts completed cases that did not pass."""
        evaluations = [record.evaluation for record in records if record.evaluation is not None]
        completed = sum(1 for record in records if record.status is CaseStatus.COMPLETED)
        passed = sum(1 for record in records if record.passed)
        return cls(
            cases=len(records),
            completed=completed,
            errors=len(records) - completed,
            passed=passed,
            failed=completed - passed,
            with_injection=sum(1 for record in records if record.case.injection is not None),
            injection_reached_model=sum(1 for e in evaluations if e.injection_reached_model),
            injection_in_model_output=sum(1 for e in evaluations if e.injection_in_model_output),
            injection_effect=sum(1 for e in evaluations if e.injection_effect),
            input_detections=sum(e.input_detections for e in evaluations),
            blocked_actions=sum(e.blocked_actions for e in evaluations),
        )

    def to_dict(self) -> dict[str, int]:
        """JSON view."""
        return {
            "cases": self.cases,
            "completed": self.completed,
            "errors": self.errors,
            "passed": self.passed,
            "failed": self.failed,
            "with_injection": self.with_injection,
            "injection_reached_model": self.injection_reached_model,
            "injection_in_model_output": self.injection_in_model_output,
            "injection_effect": self.injection_effect,
            "input_detections": self.input_detections,
            "blocked_actions": self.blocked_actions,
        }


@dataclass(frozen=True, slots=True)
class Repetition:
    """Position of a run inside a repeated measurement (``--repeat`` or several modes)."""

    group_id: str
    index: int
    count: int

    def to_dict(self) -> dict[str, object]:
        """JSON view."""
        return {"group_id": self.group_id, "index": self.index, "count": self.count}


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Complete record of a run (``run_log.json``)."""

    run_id: str
    harness_version: str
    started_at: str
    finished_at: str
    provider: str
    model: str
    defense: DefenseMode
    operation_mode: str
    repetition: Repetition | None
    config: Mapping[str, object]
    cases: tuple[CaseRecord, ...]

    @property
    def totals(self) -> RunTotals:
        """Aggregated counters."""
        return RunTotals.from_cases(self.cases)

    def to_dict(self) -> dict[str, object]:
        """JSON view (plan section 8.1)."""
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "harness_version": self.harness_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "provider": self.provider,
            "model": self.model,
            "defense": self.defense.value,
            "operation_mode": self.operation_mode,
            "repetition": self.repetition.to_dict() if self.repetition is not None else None,
            "config": dict(self.config),
            "totals": self.totals.to_dict(),
            "cases": [record.to_dict() for record in self.cases],
        }

    def summary_rows(self) -> list[dict[str, str]]:
        """One CSV row per case (plan section 8.2)."""
        run_cells = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "provider": self.provider,
            "model": self.model,
            "defense": self.defense.value,
        }
        return [record.summary_row(run_cells) for record in self.cases]
