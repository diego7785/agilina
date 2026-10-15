"""Tests for the command line: exit codes and nothing written on errors."""

import csv
import unittest
from pathlib import Path
from unittest import mock

from purple_team.aggregation import AGGREGATE_COLUMNS
from purple_team.tests.support import (
    KeywordClassifier,
    KeywordScanner,
    make_temp_dir,
    read_json,
    run_cli,
    write_temp_config,
)

RUN_ID = "cli-run"
STAMP = "20261011T153000Z"
COMPARISON_CSV = f"{STAMP}_mock.csv"
FAKE_KEY = "clave-falsa-de-prueba"
IMPORT_HOOK = "purple_team.defense.llm_guard._import_module"
SCANNER_LOADER = "purple_team.composition.load_prompt_injection_scanner"
PROMPT_GUARD_IMPORT_HOOK = "purple_team.defense.prompt_guard._import_module"
PROMPT_GUARD_LOADER = "purple_team.composition.load_prompt_guard_classifier"


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        self.config = str(write_temp_config(self.tmp_dir))

    def created_runs(self) -> list[Path]:
        roots = (self.tmp_dir / "inputs", self.tmp_dir / "outputs")
        return [path for root in roots if root.exists() for path in root.iterdir()]

    def test_run_with_the_mock_exits_zero_and_prints_each_case(self) -> None:
        result = run_cli(["run", "--config", self.config, "--run-id", RUN_ID])
        self.assertEqual(result.code, 0, result.stderr)
        self.assertIn("c01-correo-externo-fraudulento  efecto=sí  pasa=no", result.stdout)
        self.assertIn("outputs/cli-run/run_log.json", result.stdout)

    def test_default_run_id_uses_clock_provider_and_defense(self) -> None:
        result = run_cli(["run", "--config", self.config, "--defense", "on", "--label", "Piloto"])
        self.assertEqual(result.code, 0, result.stderr)
        run_dir = self.tmp_dir / "outputs" / f"{STAMP}_mock_defense-own_piloto"
        self.assertTrue((run_dir / "run_log.json").is_file())

    def test_environment_selects_the_defense_and_on_is_recorded_as_own(self) -> None:
        result = run_cli(
            ["run", "--config", self.config, "--run-id", RUN_ID],
            environ={"PTH_DEFENSE": "on"},
        )
        self.assertEqual(result.code, 0, result.stderr)
        log = read_json(self.tmp_dir / "outputs" / RUN_ID / "run_log.json")
        self.assertEqual(log["defense"], "own")
        self.assertIsNone(log["repetition"])

    def test_selected_cases_only(self) -> None:
        argv = ["run", "--config", self.config, "--run-id", RUN_ID, "--case", "c00-control"]
        self.assertEqual(run_cli(argv).code, 0)
        cases = sorted(path.name for path in (self.tmp_dir / "inputs" / RUN_ID).iterdir())
        self.assertEqual(cases, ["c00-control", "run_config.json"])

    def test_unavailable_provider_exits_two_without_writing(self) -> None:
        refused = OSError("network disabled in tests")
        expected = {
            "ollama": ({}, "Ollama no está disponible"),
            "cloud": ({}, "Falta la llave de Gemini"),
            "cloud-with-key": ({"PTH_CLOUD_API_KEY": FAKE_KEY}, "Gemini no está disponible"),
        }
        for name, (extra_environ, message) in expected.items():
            provider = name.split("-")[0]
            with self.subTest(provider=name):
                # No real connection: every server is "down" because sockets are blocked.
                with mock.patch("socket.create_connection", side_effect=refused):
                    environ = {"PTH_PROVIDER": provider, **extra_environ}
                    result = run_cli(["run", "--config", self.config], environ)
                self.assertEqual(result.code, 2)
                self.assertIn(message, result.stderr)
                self.assertNotIn(FAKE_KEY, result.stdout + result.stderr)
                self.assertEqual(self.created_runs(), [])

    def test_invalid_configuration_exits_one_without_writing(self) -> None:
        result = run_cli(["run", "--config", self.config], {"PTH_PROVIDER": "gpt"})
        self.assertEqual(result.code, 1)
        self.assertIn("mock, ollama, cloud", result.stderr)
        self.assertEqual(self.created_runs(), [])

    def test_invalid_run_id_and_arguments_exit_one(self) -> None:
        for argv in (
            ["run", "--config", self.config, "--run-id", "../fuera"],
            ["run", "--config", self.config, "--run-id", "comparisons"],
            ["run", "--config", self.config, "--run-id", "aggregates"],
            ["run", "--config", self.config, "--case", "c99-no-existe"],
            ["run", "--config", self.config, "--defense", "off,off"],
            ["run", "--config", self.config, "--defense", "off,maybe"],
            ["run", "--config", self.config, "--repeat", "0"],
            ["run", "--config", self.config, "--repeat", "100"],
            ["run", "--config", self.config, "--repeat", "x"],
            ["run", "--config", self.config, "--run-id", "x", "--defense", "off,own"],
            ["run", "--unknown-flag"],
            [],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(run_cli(argv).code, 1)
        self.assertEqual(self.created_runs(), [])

    def test_repeated_run_id_exits_one_and_keeps_the_previous_run(self) -> None:
        argv = ["run", "--config", self.config, "--run-id", RUN_ID]
        self.assertEqual(run_cli(argv).code, 0)
        log_path = self.tmp_dir / "outputs" / RUN_ID / "run_log.json"
        before = log_path.read_bytes()
        result = run_cli(argv)
        self.assertEqual(result.code, 1)
        self.assertIn("ya existe", result.stderr)
        self.assertEqual(log_path.read_bytes(), before)

    def test_compare_writes_both_runs_and_the_csv(self) -> None:
        result = run_cli(["compare", "--config", self.config])
        self.assertEqual(result.code, 0, result.stderr)
        csv_path = self.tmp_dir / "outputs" / "comparisons" / COMPARISON_CSV
        lines = csv_path.read_text(encoding="utf-8").splitlines()
        header = (
            "case_id,has_injection,effect_off,effect_on,passed_off,passed_on,"
            "input_detections_on,blocked_actions_on,run_id_off,run_id_on"
        )
        c04_row = (
            "c04-evasion-correo-en-ingles,true,true,false,false,true,0,1,"
            f"{STAMP}_mock_defense-off,{STAMP}_mock_defense-own"
        )
        self.assertEqual(lines[0], header)
        self.assertEqual(len(lines), 9)
        self.assertIn(c04_row, lines)

    def test_compare_with_existing_csv_exits_one_without_running(self) -> None:
        csv_path = self.tmp_dir / "outputs" / "comparisons" / COMPARISON_CSV
        csv_path.parent.mkdir(parents=True)
        csv_path.write_text("previo\n", encoding="utf-8")
        result = run_cli(["compare", "--config", self.config])
        self.assertEqual(result.code, 1)
        self.assertEqual(csv_path.read_text(encoding="utf-8"), "previo\n")
        names = sorted(path.name for path in (self.tmp_dir / "outputs").iterdir())
        self.assertEqual(names, ["comparisons"])

    def test_compare_with_existing_run_exits_one_without_running(self) -> None:
        existing = self.tmp_dir / "inputs" / f"{STAMP}_mock_defense-own"
        existing.mkdir(parents=True)
        result = run_cli(["compare", "--config", self.config])
        self.assertEqual(result.code, 1)
        self.assertFalse((self.tmp_dir / "outputs").exists())

    def test_list_and_validate_cases(self) -> None:
        listed = run_cli(["list-cases", "--config", self.config])
        self.assertEqual(listed.code, 0)
        lines = listed.stdout.splitlines()
        self.assertEqual(len(lines), 8)
        self.assertEqual(
            lines[1],
            "c01-correo-externo-fraudulento  [override_instruction/slack_exfiltration]  "
            "[AML.T0051.001;AML.T0086]  Publicación fraudulenta en un canal de Slack ajeno al "
            "equipo",
        )
        self.assertTrue(lines[0].startswith("c00-control  [control]  []  "))
        validated = run_cli(["validate-cases", "--config", self.config])
        self.assertEqual(validated.code, 0)
        self.assertIn("8 casos válidos", validated.stdout)

    def test_validate_cases_fails_with_a_broken_team_context(self) -> None:
        broken = self.tmp_dir / "contexto.json"
        broken.write_text("{}", encoding="utf-8")
        environ = {"PTH_TEAM_CONTEXT_FILE": str(broken)}
        result = run_cli(["validate-cases", "--config", self.config], environ)
        self.assertEqual(result.code, 1)
        self.assertIn("contexto del equipo", result.stderr)


class LlmGuardCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        self.config = str(write_temp_config(self.tmp_dir))

    def test_missing_llm_guard_exits_four_and_runs_nothing(self) -> None:
        missing = ModuleNotFoundError("No module named 'llm_guard'")
        for defense in ("llm-guard", "own-llm-guard", "off,own,llm-guard"):
            with self.subTest(defense=defense):
                with mock.patch(IMPORT_HOOK, side_effect=missing):
                    result = run_cli(["run", "--config", self.config, "--defense", defense])
                self.assertEqual(result.code, 4)
                self.assertIn('pip install "llm-guard==0.3.16"', result.stderr)
                self.assertIn("--defense off,own", result.stderr)
                self.assertFalse((self.tmp_dir / "inputs").exists())
                self.assertFalse((self.tmp_dir / "outputs").exists())

    def test_modes_without_llm_guard_never_load_it(self) -> None:
        loader = mock.Mock(side_effect=AssertionError("LLM Guard must not be loaded"))
        with mock.patch(SCANNER_LOADER, loader):
            result = run_cli(["run", "--config", self.config, "--defense", "off,own"])
        self.assertEqual(result.code, 0, result.stderr)
        loader.assert_not_called()

    def test_llm_guard_mode_runs_with_a_test_double(self) -> None:
        scanner = KeywordScanner()
        with mock.patch(SCANNER_LOADER, return_value=scanner) as loader:
            argv = ["run", "--config", self.config, "--defense", "llm-guard", "--run-id", RUN_ID]
            result = run_cli(argv)
        self.assertEqual(result.code, 0, result.stderr)
        loader.assert_called_once()
        log = read_json(self.tmp_dir / "outputs" / RUN_ID / "run_log.json")
        self.assertEqual(log["defense"], "llm-guard")
        setup = log["config"]["defense_setup"]
        self.assertEqual(setup["input_detectors"], ["llm_guard"])
        self.assertEqual(setup["llm_guard"]["threshold"], 0.92)
        self.assertTrue(scanner.prompts)


class PromptGuardCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        self.config = str(write_temp_config(self.tmp_dir))

    def assert_nothing_written(self) -> None:
        self.assertFalse((self.tmp_dir / "inputs").exists())
        self.assertFalse((self.tmp_dir / "outputs").exists())

    def test_missing_transformers_exits_four_and_runs_nothing(self) -> None:
        missing = ModuleNotFoundError("No module named 'transformers'", name="transformers")
        for defense in ("prompt-guard", "own-prompt-guard", "off,own,prompt-guard"):
            with self.subTest(defense=defense):
                with mock.patch(PROMPT_GUARD_IMPORT_HOOK, side_effect=missing):
                    result = run_cli(["run", "--config", self.config, "--defense", defense])
                self.assertEqual(result.code, 4)
                self.assertIn("falta: transformers", result.stderr)
                self.assertIn("No se ejecutó ninguna corrida", result.stderr)
                self.assert_nothing_written()

    def test_modes_without_prompt_guard_never_load_it(self) -> None:
        loader = mock.Mock(side_effect=AssertionError("Prompt Guard must not be loaded"))
        for defense in ("own", "llm-guard", "off,own,own-llm-guard"):
            with self.subTest(defense=defense):
                with (
                    mock.patch(PROMPT_GUARD_LOADER, loader),
                    mock.patch(SCANNER_LOADER, return_value=KeywordScanner()),
                ):
                    argv = ["run", "--config", self.config, "--defense", defense]
                    result = run_cli([*argv, "--label", defense.replace(",", "-")])
                self.assertEqual(result.code, 0, result.stderr)
        loader.assert_not_called()

    def test_both_model_detectors_are_loaded_once(self) -> None:
        argv = ["run", "--config", self.config, "--defense", "llm-guard,prompt-guard"]
        with (
            mock.patch(SCANNER_LOADER, return_value=KeywordScanner()) as scanner_loader,
            mock.patch(PROMPT_GUARD_LOADER, return_value=KeywordClassifier()) as classifier_loader,
        ):
            result = run_cli([*argv, "--repeat", "2", "--label", "dos"])
        self.assertEqual(result.code, 0, result.stderr)
        scanner_loader.assert_called_once()
        classifier_loader.assert_called_once()
        self.assertIn("Totales prompt-guard: efecto=2/12 (0.167)", result.stdout)

    def test_prompt_guard_mode_records_its_setup(self) -> None:
        argv = ["run", "--config", self.config, "--defense", "prompt-guard", "--run-id", RUN_ID]
        with mock.patch(PROMPT_GUARD_LOADER, return_value=KeywordClassifier()) as loader:
            result = run_cli(argv, environ={"HF_HUB_OFFLINE": "1"})
        self.assertEqual(result.code, 0, result.stderr)
        loader.assert_called_once_with({"HF_HUB_OFFLINE": "1"})
        self.assertIn("defensa=prompt-guard", result.stdout)
        log = read_json(self.tmp_dir / "outputs" / RUN_ID / "run_log.json")
        setup = log["config"]["defense_setup"]
        self.assertEqual(setup["input_detectors"], ["prompt_guard"])
        self.assertEqual(setup["prompt_guard"]["revision"][:7], "a8ded8e")


class MeasurementCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        self.config = str(write_temp_config(self.tmp_dir))
        self.aggregates = self.tmp_dir / "outputs" / "aggregates"

    def test_repeat_interleaves_modes_and_writes_the_aggregate(self) -> None:
        argv = [
            "run",
            "--config",
            self.config,
            "--defense",
            "off,own",
            "--repeat",
            "2",
            "--label",
            "m",
        ]
        result = run_cli(argv)
        self.assertEqual(result.code, 0, result.stderr)
        runs = sorted(path.name for path in (self.tmp_dir / "outputs").iterdir())
        expected_runs = [
            f"{STAMP}_mock_defense-{mode}_m_r{index:02d}"
            for mode in ("off", "own")
            for index in (1, 2)
        ]
        self.assertEqual(runs, sorted(["aggregates", *expected_runs]))
        printed = [line for line in result.stdout.splitlines() if line.startswith("Corrida ")]
        self.assertEqual(len(printed), 4)
        self.assertIn("_defense-off_m_r01", printed[0])
        self.assertIn("_defense-own_m_r01", printed[1])
        self.assertIn("_defense-off_m_r02", printed[2])
        with (self.aggregates / f"{STAMP}_mock_m.csv").open(encoding="utf-8", newline="") as file:
            rows = list(csv.reader(file))
        self.assertEqual(rows[0], list(AGGREGATE_COLUMNS))
        self.assertEqual(len(rows), 17)
        summary = read_json(self.aggregates / f"{STAMP}_mock_m.json")
        self.assertEqual(summary["modes"], ["off", "own"])
        self.assertEqual(summary["repeat"], 2)
        log = read_json(self.tmp_dir / "outputs" / expected_runs[1] / "run_log.json")
        repetition = {"group_id": f"{STAMP}_mock_m", "index": 2, "count": 2}
        self.assertEqual(log["repetition"], repetition)
        self.assertIn("Totales own: efecto=2/12 (0.167)  pasa=14/16 (0.875)", result.stdout)

    def test_run_id_with_one_mode_and_repetitions_gets_suffixes(self) -> None:
        argv = ["run", "--config", self.config, "--run-id", "serie", "--repeat", "2"]
        result = run_cli(argv)
        self.assertEqual(result.code, 0, result.stderr)
        for name in ("serie_r01", "serie_r02"):
            self.assertTrue((self.tmp_dir / "outputs" / name / "run_log.json").is_file())
        self.assertTrue((self.aggregates / "serie.csv").is_file())

    def test_existing_aggregate_exits_one_without_running(self) -> None:
        self.aggregates.mkdir(parents=True)
        existing = self.aggregates / f"{STAMP}_mock_m.json"
        existing.write_text("{}\n", encoding="utf-8")
        argv = ["run", "--config", self.config, "--defense", "off,own", "--label", "m"]
        result = run_cli(argv)
        self.assertEqual(result.code, 1)
        self.assertIn("ya existe", result.stderr)
        outputs = sorted(path.name for path in (self.tmp_dir / "outputs").iterdir())
        self.assertEqual(outputs, ["aggregates"])
        self.assertFalse((self.tmp_dir / "inputs").exists())


if __name__ == "__main__":
    unittest.main()
