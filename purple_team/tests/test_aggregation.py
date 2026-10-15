"""Tests for the aggregated summary of repeated runs (built from hand-made run records)."""

import unittest

from purple_team.aggregation import AGGREGATE_COLUMNS, aggregate_runs, mean, rate
from purple_team.cases import Case, load_cases
from purple_team.config import DefenseMode
from purple_team.evaluation.evaluator import Evaluation
from purple_team.pipeline import OPERATION_MODE
from purple_team.records import CaseRecord, CaseStatus, Repetition, RunRecord
from purple_team.tests.support import REAL_CASES_DIR

CONTROL, INJECTED = load_cases(REAL_CASES_DIR, ["c00-control", "c01-correo-externo-fraudulento"])
GROUP = "grupo"


def evaluation(case: Case, *, effect: bool, passed: bool, detections: int) -> Evaluation:
    has_injection = case.injection is not None
    flag = effect if has_injection else None
    return Evaluation(
        has_injection=has_injection,
        injection_reached_model=flag,
        injection_in_model_output=flag,
        injection_effect=flag,
        indicators_in_model_output=(),
        indicators_in_final_output=(),
        input_detections=detections,
        blocked_actions=0,
        checks=(),
        passed=passed,
    )


def record(case: Case, result: Evaluation | None) -> CaseRecord:
    status = CaseStatus.COMPLETED if result is not None else CaseStatus.ERROR
    return CaseRecord(
        case=case,
        status=status,
        timestamp="2026-10-11T15:30:00Z",
        inputs_path="inputs/x",
        outputs_path="outputs/x",
        transcript_file="cases/x/transcript.txt",
        trace=None,
        evaluation=result,
        error=None if result is not None else "ProviderRequestError: timeout",
    )


def run(run_id: str, mode: DefenseMode, index: int, cases: tuple[CaseRecord, ...]) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        harness_version="0.1.0",
        started_at="2026-10-11T15:30:00Z",
        finished_at="2026-10-11T15:30:00Z",
        provider="mock",
        model="mock-scripted-v1",
        defense=mode,
        operation_mode=OPERATION_MODE,
        repetition=Repetition(GROUP, index, 3),
        config={},
        cases=cases,
    )


def three_repetitions() -> list[RunRecord]:
    """Interleaved off/own runs; the second ``own`` run fails on the injected case."""
    runs = []
    for index in (1, 2, 3):
        off_cases = (
            record(CONTROL, evaluation(CONTROL, effect=False, passed=True, detections=0)),
            record(INJECTED, evaluation(INJECTED, effect=True, passed=False, detections=0)),
        )
        own_injected = (
            None
            if index == 2
            else evaluation(INJECTED, effect=index == 3, passed=index != 3, detections=2)
        )
        own_cases = (
            record(CONTROL, evaluation(CONTROL, effect=False, passed=True, detections=1)),
            record(INJECTED, own_injected),
        )
        runs.append(run(f"off-r{index}", DefenseMode.OFF, index, off_cases))
        runs.append(run(f"own-r{index}", DefenseMode.OWN, index, own_cases))
    return runs


class RateTest(unittest.TestCase):
    def test_rates_are_rounded_to_three_decimals(self) -> None:
        self.assertEqual(rate(2, 12), 0.167)
        self.assertEqual(rate(1, 3), 0.333)
        self.assertIsNone(rate(None, 3))
        self.assertIsNone(rate(0, 0))
        self.assertEqual(mean(3, 2), 1.5)
        self.assertIsNone(mean(0, 0))


class AggregateRunsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregate = aggregate_runs(GROUP, three_repetitions(), 3)

    def test_rows_follow_the_mode_order_and_then_the_case_id(self) -> None:
        keys = [(row.mode, row.case_id) for row in self.aggregate.rows]
        self.assertEqual(
            keys,
            [
                (DefenseMode.OFF, "c00-control"),
                (DefenseMode.OFF, "c01-correo-externo-fraudulento"),
                (DefenseMode.OWN, "c00-control"),
                (DefenseMode.OWN, "c01-correo-externo-fraudulento"),
            ],
        )
        self.assertEqual(self.aggregate.modes, (DefenseMode.OFF, DefenseMode.OWN))

    def test_controls_have_no_injection_rates(self) -> None:
        control = self.aggregate.rows[0]
        self.assertIsNone(control.injection_effect)
        self.assertIsNone(control.injection_effect_rate)
        self.assertEqual((control.passed, control.pass_rate), (3, 1.0))
        self.assertEqual(control.csv_row(GROUP, "mock", "m")["injection_effect_rate"], "n/a")

    def test_errors_are_counted_apart_and_excluded_from_the_denominators(self) -> None:
        injected_own = self.aggregate.rows[3]
        self.assertEqual((injected_own.runs, injected_own.completed), (3, 2))
        self.assertEqual(injected_own.errors, 1)
        effect = (injected_own.injection_effect, injected_own.injection_effect_rate)
        self.assertEqual(effect, (1, 0.5))
        self.assertEqual((injected_own.passed, injected_own.pass_rate), (1, 0.5))
        self.assertEqual(injected_own.input_detections_mean, 2.0)
        self.assertEqual(injected_own.run_ids, ("own-r1", "own-r2", "own-r3"))

    def test_csv_rows_use_the_documented_columns_and_formats(self) -> None:
        rows = self.aggregate.csv_rows()
        self.assertEqual(len(rows), 4)
        self.assertEqual(list(rows[0]), list(AGGREGATE_COLUMNS))
        injected_off = rows[1]
        self.assertEqual(injected_off["injection_effect_rate"], "1.000")
        self.assertEqual(injected_off["pass_rate"], "0.000")
        self.assertEqual(injected_off["input_detections_mean"], "0.00")
        self.assertEqual(injected_off["atlas_techniques"], "AML.T0051.001;AML.T0086")
        self.assertEqual(injected_off["run_ids"], "off-r1;off-r2;off-r3")
        self.assertEqual(rows[0]["atlas_techniques"], "")

    def test_per_mode_totals_and_json_view(self) -> None:
        off, own = self.aggregate.per_mode
        self.assertEqual((off.injected_case_runs, off.injection_effect_rate), (3, 1.0))
        self.assertEqual((off.passed, off.completed, off.pass_rate), (3, 6, 0.5))
        self.assertEqual((own.errors, own.injected_case_runs, own.injection_effect), (1, 2, 1))
        self.assertEqual((own.passed, own.completed, own.pass_rate), (4, 5, 0.8))
        data = self.aggregate.to_dict()
        expected_ids = {
            "off": ["off-r1", "off-r2", "off-r3"],
            "own": ["own-r1", "own-r2", "own-r3"],
        }
        self.assertEqual(data["run_ids"], expected_ids)
        rows = data["rows"]
        self.assertIsInstance(rows, list)
        if isinstance(rows, list):
            self.assertIsNone(rows[0]["injection_effect_rate"])
            self.assertEqual(rows[1]["atlas_techniques"], ["AML.T0051.001", "AML.T0086"])


if __name__ == "__main__":
    unittest.main()
