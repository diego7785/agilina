"""Runs every case of a run and produces its records."""

import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from purple_team import HARNESS_VERSION
from purple_team.cases import Case
from purple_team.clock import Clock, format_utc
from purple_team.config import DefenseMode, HarnessConfig, ProviderName
from purple_team.core.output_parser import OutputFormatError
from purple_team.core.prompts import SystemPrompt
from purple_team.errors import ConfigError
from purple_team.evaluation.evaluator import Evaluation, evaluate
from purple_team.pipeline import OPERATION_MODE, AgentPipeline, PipelineTrace
from purple_team.providers.base import ModelProvider, ProviderRequestError, RequestTrace
from purple_team.providers.mock import MockFixtureError
from purple_team.recording import RunRecorder
from purple_team.records import (
    RECORD_SCHEMA_VERSION,
    CaseRecord,
    CaseStatus,
    Repetition,
    RunRecord,
)

RUN_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
# "comparisons" holds the CSV files of the retired compare command (cycles 1-4).
RESERVED_OUTPUT_NAMES: Final = frozenset({"comparisons", "aggregates", "calibration"})
RUN_STAMP_FORMAT: Final = "%Y%m%dT%H%M%SZ"
LABEL_MAX_CHARS: Final = 30
_LABEL_INVALID_CHARS: Final = re.compile(r"[^a-z0-9-]+")
_LABEL_DASHES: Final = re.compile(r"-{2,}")
# Expected per-case failures: they are recorded as status=error and the run continues.
# ProviderRequestError covers a failed call to a real provider (network, timeout, HTTP
# status, invalid body); an unparseable MODEL answer is not an error (output_valid=false).
CASE_ERRORS: Final = (MockFixtureError, OutputFormatError, ProviderRequestError)

_LOGGER = logging.getLogger(__name__)


def format_run_stamp(started_at: datetime) -> str:
    """``AAAAMMDDTHHMMSSZ`` in UTC: lexicographic order equals chronological order."""
    return started_at.astimezone(UTC).strftime(RUN_STAMP_FORMAT)


def normalize_label(label: str) -> str:
    """Lowercase, only ``[a-z0-9-]``, at most 30 characters; ``ConfigError`` if empty."""
    cleaned = _LABEL_INVALID_CHARS.sub("-", label.casefold())
    cleaned = _LABEL_DASHES.sub("-", cleaned).strip("-")[:LABEL_MAX_CHARS].strip("-")
    if not cleaned:
        raise ConfigError(f"La etiqueta {label!r} no contiene caracteres válidos [a-z0-9-]")
    return cleaned


def make_run_id(
    started_at: datetime,
    provider: ProviderName,
    defense: DefenseMode,
    label: str | None,
) -> str:
    """``<stamp>_<provider>_defense-<mode>[_<label>]`` (plan section 7.1)."""
    run_id = f"{format_run_stamp(started_at)}_{provider.value}_defense-{defense.value}"
    if label:
        run_id = f"{run_id}_{normalize_label(label)}"
    return validate_run_id(run_id)


def validate_run_id(run_id: str) -> str:
    """Reject ids that could escape the run folders or that are reserved names."""
    if not RUN_ID_PATTERN.match(run_id) or run_id in RESERVED_OUTPUT_NAMES:
        reserved = "', '".join(sorted(RESERVED_OUTPUT_NAMES))
        message = (
            f"Run id inválido: {run_id!r}. Use letras, dígitos, '.', '_' o '-' (máximo 100), "
            f"sin '/' y distinto de '{reserved}'"
        )
        raise ConfigError(message)
    return run_id


def repeated_run_id(run_id: str, index: int) -> str:
    """``<run_id>_rNN``: id of repetition ``index`` (1-based) of a repeated measurement."""
    return validate_run_id(f"{run_id}_r{index:02d}")


class HarnessRunner:
    """Executes the cases of one run with a given pipeline and writes the records."""

    def __init__(
        self,
        *,
        config: HarnessConfig,
        provider: ModelProvider,
        pipeline: AgentPipeline,
        cases: Sequence[Case],
        system_prompt: SystemPrompt,
        recorder: RunRecorder,
        clock: Clock,
        run_id: str,
        started_at: datetime | None,
        context_record: Mapping[str, object],
        repetition: Repetition | None,
    ) -> None:
        """``started_at`` ``None`` means: read the clock when the run actually starts."""
        self._config = config
        self._provider = provider
        self._pipeline = pipeline
        self._cases = tuple(cases)
        self._system_prompt = system_prompt
        self._recorder = recorder
        self._clock = clock
        self._run_id = run_id
        self._fixed_start = started_at
        self._context_record = dict(context_record)
        self._repetition = repetition

    @property
    def run_id(self) -> str:
        """Identifier of the run."""
        return self._run_id

    @property
    def record_paths(self) -> tuple[Path, Path]:
        """Paths of ``run_log.json`` and ``run_summary.csv`` of this run."""
        return self._recorder.log_path, self._recorder.summary_path

    def preflight(self) -> None:
        """Check the provider and that the run is new, before creating anything."""
        self._provider.ensure_available()
        self._recorder.ensure_new()

    def run(self) -> RunRecord:
        """Run every case; per-case errors are recorded and the loop continues."""
        self.preflight()
        start = self._fixed_start if self._fixed_start is not None else self._clock.now()
        started_at = format_utc(start)
        config_record = {
            **self._config.to_record(),
            "system_prompt_sha256": self._system_prompt.sha256,
            **self._context_record,
        }
        self._recorder.start_run(self._run_config(config_record, started_at))
        records = tuple(self._run_case(case) for case in self._cases)
        record = RunRecord(
            run_id=self._run_id,
            harness_version=HARNESS_VERSION,
            started_at=started_at,
            finished_at=format_utc(self._clock.now()),
            provider=self._provider.name,
            model=self._provider.model,
            defense=self._config.defense,
            operation_mode=OPERATION_MODE,
            repetition=self._repetition,
            config=config_record,
            cases=records,
        )
        self._recorder.finish_run(record)
        return record

    def _run_config(self, config_record: dict[str, object], started_at: str) -> dict[str, object]:
        repetition = self._repetition.to_dict() if self._repetition is not None else None
        return {
            "schema_version": RECORD_SCHEMA_VERSION,
            "harness_version": HARNESS_VERSION,
            "run_id": self._run_id,
            "started_at": started_at,
            "provider": self._provider.name,
            "model": self._provider.model,
            "defense": self._config.defense.value,
            "operation_mode": OPERATION_MODE,
            "repetition": repetition,
            "config": config_record,
        }

    def _run_case(self, case: Case) -> CaseRecord:
        timestamp = format_utc(self._clock.now())
        request_trace = RequestTrace(run_id=self._run_id, case_id=case.case_id)
        try:
            trace = self._pipeline.process(case.transcript, self._system_prompt, request_trace)
        except CASE_ERRORS as exc:
            self._recorder.write_case_inputs(case, self._system_prompt, None)
            return self._error_record(case, timestamp, None, exc)
        evaluation = evaluate(case, trace)
        try:
            self._recorder.write_case_inputs(case, self._system_prompt, trace)
            self._recorder.write_case_outputs(case, trace, evaluation)
        except OSError as exc:
            return self._error_record(case, timestamp, trace, exc)
        return self._case_record(case, timestamp, trace, CaseStatus.COMPLETED, evaluation, None)

    def _error_record(
        self,
        case: Case,
        timestamp: str,
        trace: PipelineTrace | None,
        error: Exception,
    ) -> CaseRecord:
        _LOGGER.warning("Case %s failed: %s", case.case_id, error)
        self._recorder.write_case_error(case, error)
        message = f"{type(error).__name__}: {error}"
        return self._case_record(case, timestamp, trace, CaseStatus.ERROR, None, message)

    def _case_record(
        self,
        case: Case,
        timestamp: str,
        trace: PipelineTrace | None,
        status: CaseStatus,
        evaluation: Evaluation | None,
        error: str | None,
    ) -> CaseRecord:
        recorder = self._recorder
        return CaseRecord(
            case=case,
            status=status,
            timestamp=timestamp,
            inputs_path=recorder.display(recorder.case_inputs_dir(case.case_id)),
            outputs_path=recorder.display(recorder.case_outputs_dir(case.case_id)),
            transcript_file=recorder.display(case.transcript_path),
            trace=trace,
            evaluation=evaluation,
            error=error,
        )
