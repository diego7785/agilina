"""Writes the inputs and outputs of a run: ``inputs/<run_id>/<case_id>/`` and ``outputs/...``.

Every file is created in mode ``"x"``: an existing run is never overwritten.
"""

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from purple_team.cases import Case
from purple_team.core.prompts import SystemPrompt
from purple_team.errors import RunExistsError
from purple_team.evaluation.evaluator import Evaluation
from purple_team.paths import display_path
from purple_team.pipeline import PipelineTrace
from purple_team.records import SUMMARY_COLUMNS, RunRecord

ENCODING: Final = "utf-8"
LINE_END: Final = "\n"
CREATE_ONLY: Final = "x"
RUN_CONFIG_FILE: Final = "run_config.json"
RUN_LOG_FILE: Final = "run_log.json"
RUN_SUMMARY_FILE: Final = "run_summary.csv"
CASE_DEFINITION_FILE: Final = "case.json"
ORIGINAL_TRANSCRIPT_FILE: Final = "transcript.original.txt"
MODEL_TRANSCRIPT_FILE: Final = "transcript.model.txt"
SYSTEM_PROMPT_FILE: Final = "system_prompt.txt"
MODEL_REQUEST_FILE: Final = "model_request.json"
INPUT_GUARD_FILE: Final = "input_guard.json"
RAW_OUTPUT_FILE: Final = "model_output.raw.txt"
THINKING_FILE: Final = "model_thinking.txt"
PARSED_OUTPUT_FILE: Final = "model_output.parsed.json"
OUTPUT_GUARD_FILE: Final = "output_guard.json"
FINAL_OUTPUT_FILE: Final = "final_output.json"
TOOL_CALLS_FILE: Final = "tool_calls.json"
SYSTEM_OUTPUTS_FILE: Final = "system_outputs.json"
EVALUATION_FILE: Final = "evaluation.json"
ERROR_FILE: Final = "error.json"


def write_json(path: Path, data: object) -> None:
    """Readable JSON (UTF-8, LF, 2 spaces, final newline); fails if the file exists."""
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + LINE_END)


def write_text(path: Path, text: str) -> None:
    """UTF-8 text with LF line ends; fails if the file exists."""
    with path.open(CREATE_ONLY, encoding=ENCODING, newline=LINE_END) as handle:
        handle.write(text)


def write_summary_csv(
    path: Path,
    rows: Sequence[Mapping[str, str]],
    columns: Sequence[str],
) -> None:
    """CSV with header, ``,`` separator and ``\\n`` line ends; fails if the file exists."""
    with path.open(CREATE_ONLY, encoding=ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator=LINE_END)
        writer.writeheader()
        writer.writerows(rows)


class RunRecorder:
    """Owns the folders of one run and writes every record file."""

    def __init__(
        self,
        *,
        run_id: str,
        inputs_root: Path,
        outputs_root: Path,
        base_dir: Path,
    ) -> None:
        self._run_id = run_id
        self._base_dir = base_dir
        self.run_inputs_dir = inputs_root / run_id
        self.run_outputs_dir = outputs_root / run_id

    @property
    def run_id(self) -> str:
        """Identifier of the run."""
        return self._run_id

    @property
    def log_path(self) -> Path:
        """``outputs/<run_id>/run_log.json``."""
        return self.run_outputs_dir / RUN_LOG_FILE

    @property
    def summary_path(self) -> Path:
        """``outputs/<run_id>/run_summary.csv``."""
        return self.run_outputs_dir / RUN_SUMMARY_FILE

    def display(self, path: Path) -> str:
        """Path as written to the records (plan section 7.3)."""
        return display_path(path, self._base_dir)

    def case_inputs_dir(self, case_id: str) -> Path:
        """``inputs/<run_id>/<case_id>``."""
        return self.run_inputs_dir / case_id

    def case_outputs_dir(self, case_id: str) -> Path:
        """``outputs/<run_id>/<case_id>``."""
        return self.run_outputs_dir / case_id

    def ensure_new(self) -> None:
        """Raise ``RunExistsError`` if any folder of the run already exists."""
        if self.run_inputs_dir.exists() or self.run_outputs_dir.exists():
            raise RunExistsError(self._exists_message())

    def start_run(self, config_record: Mapping[str, object]) -> None:
        """Create both run folders (never reusing them) and write ``run_config.json``."""
        self.ensure_new()
        try:
            self.run_inputs_dir.mkdir(parents=True)
            self.run_outputs_dir.mkdir(parents=True)
        except FileExistsError as exc:
            raise RunExistsError(self._exists_message()) from exc
        write_json(self.run_inputs_dir / RUN_CONFIG_FILE, dict(config_record))

    def write_case_inputs(
        self,
        case: Case,
        system_prompt: SystemPrompt,
        trace: PipelineTrace | None,
    ) -> Path:
        """Write what the case used; without a trace only the static inputs are written."""
        folder = self.case_inputs_dir(case.case_id)
        folder.mkdir()
        ids = self._ids(case)
        definition = {
            **ids,
            "source_file": self.display(case.directory / CASE_DEFINITION_FILE),
            "definition": dict(case.raw_definition),
        }
        write_json(folder / CASE_DEFINITION_FILE, definition)
        write_text(folder / ORIGINAL_TRANSCRIPT_FILE, case.transcript)
        write_text(folder / SYSTEM_PROMPT_FILE, system_prompt.text)
        if trace is None:
            return folder
        request = trace.closing.request
        response = trace.closing.response
        write_text(folder / MODEL_TRANSCRIPT_FILE, trace.input_screening.transcript)
        model_request = {
            **ids,
            "provider": response.provider,
            "model": response.model,
            "temperature": request.temperature,
            "system_prompt_sha256": system_prompt.sha256,
            "user_content": request.user_content,
        }
        write_json(folder / MODEL_REQUEST_FILE, model_request)
        write_json(folder / INPUT_GUARD_FILE, {**ids, **trace.input_screening.to_dict()})
        return folder

    def write_case_outputs(self, case: Case, trace: PipelineTrace, evaluation: Evaluation) -> Path:
        """Write the model output, both guard decisions, the tool calls, the automatic system
        outputs and the evaluation."""
        folder = self.case_outputs_dir(case.case_id)
        folder.mkdir()
        ids = self._ids(case)
        closing = trace.closing
        parsed = closing.output.to_dict() if closing.output is not None else None
        final_output = trace.final_output
        write_text(folder / RAW_OUTPUT_FILE, closing.response.text)
        if closing.response.thinking is not None:
            write_text(folder / THINKING_FILE, closing.response.thinking)
        parsed_record = {
            **ids,
            "valid": closing.output is not None,
            "parse_error": closing.parse_error,
            "output": parsed,
        }
        write_json(folder / PARSED_OUTPUT_FILE, parsed_record)
        write_json(folder / OUTPUT_GUARD_FILE, {**ids, **self._output_guard_record(trace)})
        final_record = {
            **ids,
            "output": final_output.to_dict() if final_output is not None else None,
        }
        write_json(folder / FINAL_OUTPUT_FILE, final_record)
        tool_calls = [call.to_dict() for call in trace.tool_calls]
        write_json(folder / TOOL_CALLS_FILE, {**ids, "tool_calls": tool_calls})
        system_outputs = [record.to_dict() for record in trace.system_outputs]
        write_json(folder / SYSTEM_OUTPUTS_FILE, {**ids, "system_outputs": system_outputs})
        write_json(folder / EVALUATION_FILE, {**ids, **evaluation.to_dict()})
        return folder

    def write_case_error(self, case: Case, error: Exception) -> Path:
        """Write ``error.json`` for a case that could not complete."""
        folder = self.case_outputs_dir(case.case_id)
        folder.mkdir(exist_ok=True)
        record = {**self._ids(case), "error_type": type(error).__name__, "message": str(error)}
        write_json(folder / ERROR_FILE, record)
        return folder

    def finish_run(self, record: RunRecord) -> tuple[Path, Path]:
        """Write ``run_log.json`` and ``run_summary.csv``; return both paths."""
        write_json(self.log_path, record.to_dict())
        write_summary_csv(self.summary_path, record.summary_rows(), SUMMARY_COLUMNS)
        return self.log_path, self.summary_path

    def _ids(self, case: Case) -> dict[str, str]:
        return {"run_id": self._run_id, "case_id": case.case_id}

    def _exists_message(self) -> str:
        return f"La corrida {self._run_id} ya existe; elige otro --run-id o --label"

    @staticmethod
    def _output_guard_record(trace: PipelineTrace) -> dict[str, object]:
        screening = trace.output_screening
        if screening is None:
            mode = trace.input_screening.mode.value
            return {"mode": mode, "applied": False, "blocked": []}
        return {**screening.to_dict(), "applied": True}
