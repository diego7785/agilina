"""Tests for the record writers and the run folders."""

import csv
import json
import unittest
from dataclasses import replace
from pathlib import Path

from purple_team.cases import Case, load_cases, mock_scripts_for
from purple_team.config import DefenseMode
from purple_team.core.ceremony import CeremonyCloser
from purple_team.core.prompts import load_system_prompt
from purple_team.errors import RunExistsError
from purple_team.evaluation.evaluator import evaluate
from purple_team.pipeline import OPERATION_MODE, PipelineTrace
from purple_team.providers.base import RequestTrace
from purple_team.providers.mock import MockProvider
from purple_team.recording import RunRecorder, write_json, write_summary_csv
from purple_team.records import SUMMARY_COLUMNS, CaseRecord, CaseStatus, Repetition, RunRecord
from purple_team.tests.support import (
    REAL_CASES_DIR,
    REAL_SYSTEM_PROMPT,
    make_temp_dir,
    own_defense,
    read_json,
    real_team_context,
    simulated_pipeline,
)

RUN_ID = "test-run"
CASE = load_cases(REAL_CASES_DIR, ["c04-evasion-correo-en-ingles"])[0]
PROMPT = load_system_prompt(REAL_SYSTEM_PROMPT)


def trace_for(case: Case) -> PipelineTrace:
    closer = CeremonyCloser(MockProvider(mock_scripts_for([case])), 0.0, real_team_context())
    defense = own_defense()
    pipeline = simulated_pipeline(closer, defense)
    return pipeline.process(case.transcript, PROMPT, RequestTrace(RUN_ID, case.case_id))


class WritersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)

    def test_json_is_readable_utf8_and_never_overwritten(self) -> None:
        path = self.tmp_dir / "data.json"
        write_json(path, {"texto": "migración", "n": 1})
        self.assertEqual(
            path.read_bytes(),
            '{\n  "texto": "migración",\n  "n": 1\n}\n'.encode(),
        )
        with self.assertRaises(FileExistsError):
            write_json(path, {})

    def test_csv_has_header_rows_and_lf_line_ends(self) -> None:
        path = self.tmp_dir / "rows.csv"
        write_summary_csv(path, [{"a": "1", "b": "x,y"}], ["a", "b"])
        self.assertEqual(path.read_bytes(), b'a,b\n1,"x,y"\n')


class RunRecorderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = make_temp_dir(self)
        self.recorder = RunRecorder(
            run_id=RUN_ID,
            inputs_root=self.base / "inputs",
            outputs_root=self.base / "outputs",
            base_dir=self.base,
        )

    def test_start_run_creates_folders_and_run_config(self) -> None:
        self.recorder.ensure_new()
        self.recorder.start_run({"run_id": RUN_ID})
        self.assertTrue((self.base / "outputs" / RUN_ID).is_dir())
        run_config = read_json(self.base / "inputs" / RUN_ID / "run_config.json")
        self.assertEqual(run_config["run_id"], RUN_ID)

    def test_existing_run_is_rejected_before_writing(self) -> None:
        (self.base / "outputs" / RUN_ID).mkdir(parents=True)
        with self.assertRaises(RunExistsError):
            self.recorder.ensure_new()
        with self.assertRaises(RunExistsError):
            self.recorder.start_run({})
        self.assertFalse((self.base / "inputs" / RUN_ID).exists())

    def test_case_files_carry_run_and_case_ids(self) -> None:
        trace = trace_for(CASE)
        evaluation = evaluate(CASE, trace)
        self.recorder.start_run({})
        inputs = self.recorder.write_case_inputs(CASE, PROMPT, trace)
        outputs = self.recorder.write_case_outputs(CASE, trace, evaluation)
        expected_inputs = {
            "case.json",
            "transcript.original.txt",
            "transcript.model.txt",
            "system_prompt.txt",
            "model_request.json",
            "input_guard.json",
        }
        expected_outputs = {
            "model_output.raw.txt",
            "model_output.parsed.json",
            "output_guard.json",
            "final_output.json",
            "tool_calls.json",
            "system_outputs.json",
            "evaluation.json",
        }
        self.assertEqual({path.name for path in inputs.iterdir()}, expected_inputs)
        self.assertEqual({path.name for path in outputs.iterdir()}, expected_outputs)
        for path in [*inputs.glob("*.json"), *outputs.glob("*.json")]:
            with self.subTest(file=path.name):
                data = read_json(path)
                self.assertEqual(data["run_id"], RUN_ID)
                self.assertEqual(data["case_id"], CASE.case_id)
        guard = read_json(outputs / "output_guard.json")
        self.assertEqual(guard["mode"], "own")
        blocked = guard["blocked"]
        self.assertIsInstance(blocked, list)
        if isinstance(blocked, list):
            self.assertEqual(blocked[0]["reason"], "slack_user_not_allowed")
        input_guard = read_json(inputs / "input_guard.json")
        self.assertEqual(input_guard["detectors"], ["regex"])
        request = read_json(inputs / "model_request.json")
        self.assertEqual(request["system_prompt_sha256"], PROMPT.sha256)

    def test_thinking_is_written_to_its_own_file(self) -> None:
        trace = trace_for(CASE)
        response = replace(trace.closing.response, thinking="razonamiento del modelo")
        trace = replace(trace, closing=replace(trace.closing, response=response))
        self.recorder.start_run({})
        outputs = self.recorder.write_case_outputs(CASE, trace, evaluate(CASE, trace))
        thinking = outputs / "model_thinking.txt"
        self.assertEqual(thinking.read_text(encoding="utf-8"), "razonamiento del modelo")
        raw = (outputs / "model_output.raw.txt").read_text(encoding="utf-8")
        self.assertNotIn("razonamiento del modelo", raw)

    def test_inputs_without_trace_only_have_static_files(self) -> None:
        self.recorder.start_run({})
        inputs = self.recorder.write_case_inputs(CASE, PROMPT, None)
        self.assertEqual(
            {path.name for path in inputs.iterdir()},
            {"case.json", "transcript.original.txt", "system_prompt.txt"},
        )
        definition = read_json(inputs / "case.json")
        self.assertEqual(definition["definition"], dict(CASE.raw_definition))

    def test_error_json_describes_the_failure(self) -> None:
        self.recorder.start_run({})
        folder = self.recorder.write_case_error(CASE, LookupError("sin guion"))
        error = read_json(folder / "error.json")
        self.assertEqual(error["error_type"], "LookupError")
        self.assertEqual(error["message"], "sin guion")

    def test_finish_run_writes_log_and_summary(self) -> None:
        trace = trace_for(CASE)
        record = CaseRecord(
            case=CASE,
            status=CaseStatus.COMPLETED,
            timestamp="2026-10-11T15:30:00Z",
            inputs_path=self.recorder.display(self.recorder.case_inputs_dir(CASE.case_id)),
            outputs_path=self.recorder.display(self.recorder.case_outputs_dir(CASE.case_id)),
            transcript_file=self.recorder.display(CASE.transcript_path),
            trace=trace,
            evaluation=evaluate(CASE, trace),
            error=None,
        )
        run = RunRecord(
            run_id=RUN_ID,
            harness_version="0.1.0",
            started_at="2026-10-11T15:30:00Z",
            finished_at="2026-10-11T15:30:00Z",
            provider="mock",
            model="mock-scripted-v1",
            defense=DefenseMode.OWN,
            operation_mode=OPERATION_MODE,
            repetition=Repetition(group_id="grupo", index=2, count=3),
            config={},
            cases=(record,),
        )
        self.recorder.start_run({})
        log_path, summary_path = self.recorder.finish_run(run)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["totals"]["blocked_actions"], 1)
        self.assertEqual(log["cases"][0]["paths"]["outputs"], f"outputs/{RUN_ID}/{CASE.case_id}")
        lines = summary_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], ",".join(SUMMARY_COLUMNS))
        self.assertEqual(len(lines), 2)
        self.assertIn(",AML.T0051.001;AML.T0086,", lines[1])
        self.assertEqual(log["schema_version"], 3)
        self.assertEqual(log["repetition"], {"group_id": "grupo", "index": 2, "count": 3})
        self.assertEqual(
            log["cases"][0]["atlas_techniques"][1],
            {"id": "AML.T0086", "name": "Exfiltration via AI Agent Tool Invocation"},
        )
        self.assertIn("@partner-review", json.dumps(log["cases"][0]["output_guard"]))
        case_log = log["cases"][0]
        self.assertEqual(list(case_log)[-3:], ["tool_calls", "system_outputs", "evaluation"])
        self.assertEqual(len(case_log["system_outputs"]), 5)
        self.assertEqual({call["origin"] for call in case_log["tool_calls"]}, {"model"})
        row = next(csv.DictReader(lines))
        self.assertEqual((row["tool_calls"], row["system_outputs"]), ("3", "5"))

    def test_paths_outside_the_base_are_absolute(self) -> None:
        self.assertTrue(Path(self.recorder.display(CASE.transcript_path)).is_absolute())


if __name__ == "__main__":
    unittest.main()
