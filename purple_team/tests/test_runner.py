"""Tests for run ids, the preflight and the per-case error handling of the runner."""

import unittest
from collections.abc import Mapping
from pathlib import Path

from purple_team.cases import load_cases, mock_scripts_for
from purple_team.config import DefenseMode, ProviderName, load_config
from purple_team.core.ceremony import CeremonyCloser
from purple_team.core.prompts import load_system_prompt
from purple_team.defense.layered import NoDefense
from purple_team.errors import ConfigError
from purple_team.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderRequestError,
    ProviderUnavailableError,
)
from purple_team.providers.mock import MockProvider, MockScript
from purple_team.providers.ollama import OllamaProvider
from purple_team.recording import RunRecorder
from purple_team.records import CaseStatus, Repetition
from purple_team.runner import (
    HarnessRunner,
    make_run_id,
    normalize_label,
    repeated_run_id,
    validate_run_id,
)
from purple_team.tests.support import (
    FIXED_INSTANT,
    FixedClock,
    make_temp_dir,
    read_json,
    real_team_context,
    simulated_pipeline,
    write_temp_config,
)

CASE_IDS = ["c00-control", "c01-correo-externo-fraudulento", "c02-exfiltracion-onedrive"]
FAILING_CASE = "c01-correo-externo-fraudulento"


class RefusingTransport:
    """Ollama transport whose server is down (no connection is opened)."""

    def request_json(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | None,
        timeout: float,
    ) -> Mapping[str, object]:
        raise ProviderRequestError(f"connection refused: {method} {url}")


class FlakyProvider:
    """Delegates to the mock but fails like a network error on one case."""

    def __init__(self, delegate: MockProvider) -> None:
        self._delegate = delegate

    @property
    def name(self) -> str:
        return "flaky"

    @property
    def model(self) -> str:
        return "flaky-1"

    def ensure_available(self) -> None:
        self._delegate.ensure_available()

    def complete(self, request: ModelRequest) -> ModelResponse:
        if request.trace.case_id == FAILING_CASE:
            raise ProviderRequestError("No se pudo conectar con Ollama: timed out")
        return self._delegate.complete(request)


class RunIdTest(unittest.TestCase):
    def test_run_id_follows_the_naming_rule(self) -> None:
        run_id = make_run_id(FIXED_INSTANT, ProviderName.MOCK, DefenseMode.OFF, None)
        self.assertEqual(run_id, "20261011T153000Z_mock_defense-off")

    def test_label_is_normalized(self) -> None:
        mode = DefenseMode.LLM_GUARD_DEFAULT
        run_id = make_run_id(FIXED_INSTANT, ProviderName.MOCK, mode, " Piloto #1 ")
        self.assertEqual(run_id, "20261011T153000Z_mock_defense-llm-guard-default_piloto-1")
        self.assertEqual(len(normalize_label("x" * 80)), 30)
        with self.assertRaises(ConfigError):
            normalize_label("¿?")

    def test_unsafe_or_reserved_run_ids_are_rejected(self) -> None:
        reserved = ("comparisons", "aggregates", "calibration")
        for run_id in ("../fuera", "a/b", ".oculta", "", *reserved, "x" * 101):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ConfigError):
                    validate_run_id(run_id)
        self.assertEqual(validate_run_id("determinism-run-a"), "determinism-run-a")

    def test_repeated_run_ids_have_a_two_digit_suffix(self) -> None:
        self.assertEqual(repeated_run_id("grupo", 3), "grupo_r03")
        self.assertEqual(repeated_run_id("grupo", 12), "grupo_r12")


class HarnessRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        config_file = write_temp_config(self.tmp_dir)
        self.config = load_config(cli_overrides={"config": str(config_file)}, environ={})
        self.cases = load_cases(self.config.cases_dir, CASE_IDS)
        self.prompt = load_system_prompt(self.config.system_prompt_file)

    def runner(
        self,
        provider: ModelProvider,
        run_id: str = "run-1",
        repetition: Repetition | None = None,
    ) -> HarnessRunner:
        closer = CeremonyCloser(provider, self.config.temperature, real_team_context())
        recorder = RunRecorder(
            run_id=run_id,
            inputs_root=self.config.inputs_dir,
            outputs_root=self.config.outputs_dir,
            base_dir=self.config.base_dir,
        )
        return HarnessRunner(
            config=self.config,
            provider=provider,
            pipeline=simulated_pipeline(closer, NoDefense()),
            cases=self.cases,
            system_prompt=self.prompt,
            recorder=recorder,
            clock=FixedClock(),
            run_id=run_id,
            started_at=FIXED_INSTANT,
            context_record={"atlas_version": "2026.09"},
            repetition=repetition,
        )

    def scripts_without(self, case_id: str) -> Mapping[str, MockScript]:
        scripts = mock_scripts_for(self.cases)
        del scripts[case_id]
        return scripts

    def test_unavailable_provider_stops_before_creating_folders(self) -> None:
        runner = self.runner(OllamaProvider(self.config.ollama, RefusingTransport()))
        with self.assertRaises(ProviderUnavailableError):
            runner.run()
        self.assertFalse((self.tmp_dir / "inputs").exists())
        self.assertFalse((self.tmp_dir / "outputs").exists())

    def test_completed_run_records_every_case(self) -> None:
        record = self.runner(MockProvider(mock_scripts_for(self.cases))).run()
        self.assertEqual([case.status for case in record.cases], [CaseStatus.COMPLETED] * 3)
        self.assertEqual(record.started_at, "2026-10-11T15:30:00Z")
        # c01 and c02 fall for the injection; the system policy blocks both external items.
        self.assertEqual(record.totals.injection_in_model_output, 2)
        self.assertEqual(record.totals.injection_effect, 0)
        self.assertEqual(record.totals.blocked_actions, 2)
        run_config = read_json(self.tmp_dir / "inputs" / "run-1" / "run_config.json")
        self.assertEqual(run_config["run_id"], "run-1")
        self.assertIsNone(run_config["repetition"])
        config = run_config["config"]
        self.assertIsInstance(config, dict)
        if isinstance(config, dict):
            self.assertEqual(config["atlas_version"], "2026.09")

    def test_repetition_is_recorded_in_the_run_config_and_the_log(self) -> None:
        repetition = Repetition(group_id="grupo", index=1, count=2)
        provider = MockProvider(mock_scripts_for(self.cases))
        record = self.runner(provider, repetition=repetition).run()
        self.assertEqual(record.repetition, repetition)
        log = read_json(self.tmp_dir / "outputs" / "run-1" / "run_log.json")
        self.assertEqual(log["repetition"], {"group_id": "grupo", "index": 1, "count": 2})

    def test_case_error_is_recorded_and_the_loop_continues(self) -> None:
        provider = MockProvider(self.scripts_without("c01-correo-externo-fraudulento"))
        with self.assertLogs("purple_team.runner", level="WARNING"):
            record = self.runner(provider).run()
        statuses = [case.status for case in record.cases]
        self.assertEqual(statuses, [CaseStatus.COMPLETED, CaseStatus.ERROR, CaseStatus.COMPLETED])
        self.assertEqual(record.totals.errors, 1)
        failed = record.cases[1]
        self.assertIsNotNone(failed.error)
        self.assertIn("MockFixtureError", failed.error or "")
        outputs = Path(self.tmp_dir / "outputs" / "run-1" / "c01-correo-externo-fraudulento")
        self.assertEqual([path.name for path in outputs.iterdir()], ["error.json"])
        log = read_json(self.tmp_dir / "outputs" / "run-1" / "run_log.json")
        totals = log["totals"]
        self.assertIsInstance(totals, dict)
        if isinstance(totals, dict):
            self.assertEqual(totals["errors"], 1)
            self.assertEqual(totals["completed"], 2)

    def test_provider_request_error_is_a_case_error_and_the_run_continues(self) -> None:
        provider = FlakyProvider(MockProvider(mock_scripts_for(self.cases)))
        with self.assertLogs("purple_team.runner", level="WARNING"):
            record = self.runner(provider).run()
        statuses = [case.status for case in record.cases]
        self.assertEqual(statuses, [CaseStatus.COMPLETED, CaseStatus.ERROR, CaseStatus.COMPLETED])
        self.assertIn("ProviderRequestError: No se pudo conectar", record.cases[1].error or "")
        error = read_json(self.tmp_dir / "outputs" / "run-1" / FAILING_CASE / "error.json")
        self.assertEqual(error["error_type"], "ProviderRequestError")
        log = read_json(self.tmp_dir / "outputs" / "run-1" / "run_log.json")
        self.assertEqual(log["totals"], record.totals.to_dict())
        self.assertEqual(record.totals.errors, 1)

    def test_existing_run_is_never_overwritten(self) -> None:
        provider = MockProvider(mock_scripts_for(self.cases))
        self.runner(provider).run()
        log_path = self.tmp_dir / "outputs" / "run-1" / "run_log.json"
        before = log_path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.runner(provider).run()
        self.assertEqual(log_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
