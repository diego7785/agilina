"""Tests for the configuration precedence and validation."""

import unittest

from purple_team.config import (
    BASELINE_SCANNER,
    DEFAULT_CONFIG_FILE,
    MOCK_TEMPERATURE,
    CloudThinkingLevel,
    ConfigSource,
    DefenseMode,
    LlmGuardMatchType,
    OllamaFormat,
    ProviderName,
    ScannerModel,
    ScannerSettings,
    load_config,
    parse_defense_modes,
)
from purple_team.errors import ConfigError
from purple_team.tests.support import (
    PURPLE_TEAM_DIR,
    REAL_TEAM_CONTEXT,
    make_temp_dir,
    write_temp_config,
)


class DefaultConfigTest(unittest.TestCase):
    def test_versioned_file_selects_mock_without_defense(self) -> None:
        config = load_config(cli_overrides={}, environ={})
        self.assertIs(config.provider, ProviderName.MOCK)
        self.assertIs(config.defense, DefenseMode.OFF)
        self.assertEqual(config.config_file, DEFAULT_CONFIG_FILE)
        self.assertEqual(config.base_dir, PURPLE_TEAM_DIR)
        self.assertEqual(config.cases_dir, PURPLE_TEAM_DIR / "cases")
        self.assertEqual(config.team_context_file, REAL_TEAM_CONTEXT)
        self.assertEqual(config.max_content_chars, 1500)
        self.assertEqual(config.calibration_dir, PURPLE_TEAM_DIR / "calibration")
        self.assertIs(config.llm_guard_tuned.model, ScannerModel.PROTECTAI_V2)
        self.assertIs(config.prompt_guard_2.model, ScannerModel.PROMPT_GUARD_2)

    def test_defaults_in_code_match_the_versioned_file(self) -> None:
        config = load_config(cli_overrides={}, environ={})
        self.assertEqual(config.sources["provider"], ConfigSource.FILE)
        empty_dir = make_temp_dir(self)
        empty_file = empty_dir / "empty.toml"
        empty_file.write_text("", encoding="utf-8")
        from_code = load_config(cli_overrides={"config": str(empty_file)}, environ={})
        self.assertEqual(from_code.sources["provider"], ConfigSource.DEFAULT)
        self.assertEqual(from_code.ollama, config.ollama)
        self.assertEqual(from_code.cloud, config.cloud)
        self.assertEqual(from_code.max_content_chars, config.max_content_chars)
        self.assertEqual(from_code.llm_guard_tuned, config.llm_guard_tuned)
        self.assertEqual(from_code.prompt_guard_2, config.prompt_guard_2)
        self.assertEqual(
            from_code.display(from_code.calibration_dir),
            config.display(config.calibration_dir),
        )
        shown_from_code = from_code.display(from_code.team_context_file)
        self.assertEqual(shown_from_code, config.display(config.team_context_file))
        self.assertEqual(from_code.provider, config.provider)
        self.assertEqual(from_code.defense, config.defense)


class PrecedenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        self.config_file = write_temp_config(
            self.tmp_dir,
            harness_lines=['defense = "llm-guard-tuned"'],
        )

    def test_file_overrides_defaults(self) -> None:
        config = load_config(cli_overrides={"config": str(self.config_file)}, environ={})
        self.assertIs(config.defense, DefenseMode.LLM_GUARD_TUNED)
        self.assertEqual(config.sources["defense"], ConfigSource.FILE)
        self.assertEqual(config.sources["config_file"], ConfigSource.CLI)

    def test_environment_overrides_file(self) -> None:
        environ = {"PTH_CONFIG": str(self.config_file), "PTH_DEFENSE": "off"}
        config = load_config(cli_overrides={}, environ=environ)
        self.assertIs(config.defense, DefenseMode.OFF)
        self.assertEqual(config.sources["defense"], ConfigSource.ENV)
        self.assertEqual(config.sources["config_file"], ConfigSource.ENV)

    def test_cli_overrides_environment(self) -> None:
        environ = {"PTH_CONFIG": str(self.config_file), "PTH_PROVIDER": "ollama"}
        config = load_config(cli_overrides={"provider": "cloud"}, environ=environ)
        self.assertIs(config.provider, ProviderName.CLOUD)
        self.assertEqual(config.sources["provider"], ConfigSource.CLI)

    def test_cli_config_wins_over_environment_config(self) -> None:
        environ = {"PTH_CONFIG": str(DEFAULT_CONFIG_FILE)}
        config = load_config(cli_overrides={"config": str(self.config_file)}, environ=environ)
        self.assertEqual(config.config_file, self.config_file.resolve())

    def test_relative_paths_resolve_against_the_config_folder(self) -> None:
        config = load_config(cli_overrides={"config": str(self.config_file)}, environ={})
        self.assertEqual(config.base_dir, self.tmp_dir.resolve())
        self.assertEqual(config.inputs_dir, self.tmp_dir.resolve() / "inputs")
        self.assertEqual(config.outputs_dir, self.tmp_dir.resolve() / "outputs")

    def test_empty_environment_values_are_ignored(self) -> None:
        environ = {"PTH_CONFIG": str(self.config_file), "PTH_DEFENSE": ""}
        config = load_config(cli_overrides={}, environ=environ)
        self.assertIs(config.defense, DefenseMode.LLM_GUARD_TUNED)

    def test_team_context_file_from_file_and_environment(self) -> None:
        config = load_config(cli_overrides={"config": str(self.config_file)}, environ={})
        self.assertEqual(config.team_context_file, REAL_TEAM_CONTEXT)
        environ = {"PTH_CONFIG": str(self.config_file), "PTH_TEAM_CONTEXT_FILE": "otro.json"}
        from_env = load_config(cli_overrides={}, environ=environ)
        self.assertEqual(from_env.team_context_file, self.tmp_dir.resolve() / "otro.json")
        self.assertEqual(from_env.sources["team_context_file"], ConfigSource.ENV)


class DefenseModeTest(unittest.TestCase):
    def test_every_mode_is_accepted(self) -> None:
        self.assertEqual(
            [mode.value for mode in DefenseMode],
            ["off", "llm-guard-default", "llm-guard-tuned", "prompt-guard-2"],
        )
        for mode in DefenseMode:
            with self.subTest(mode=mode):
                config = load_config(cli_overrides={"defense": mode.value}, environ={})
                self.assertIs(config.defense, mode)

    def test_lists_of_modes_keep_the_order(self) -> None:
        modes = parse_defense_modes("prompt-guard-2, off,llm-guard-tuned,llm-guard-default")
        expected = (
            DefenseMode.PROMPT_GUARD_2,
            DefenseMode.OFF,
            DefenseMode.LLM_GUARD_TUNED,
            DefenseMode.LLM_GUARD_DEFAULT,
        )
        self.assertEqual(modes, expected)

    def test_scanner_modes_from_the_environment_and_the_command_line(self) -> None:
        from_env = load_config(cli_overrides={}, environ={"PTH_DEFENSE": "prompt-guard-2"})
        self.assertIs(from_env.defense, DefenseMode.PROMPT_GUARD_2)
        self.assertEqual(from_env.sources["defense"], ConfigSource.ENV)
        from_cli = load_config(cli_overrides={"defense": "llm-guard-default"}, environ={})
        self.assertIs(from_cli.defense, DefenseMode.LLM_GUARD_DEFAULT)
        self.assertEqual(from_cli.to_record()["defense"], "llm-guard-default")

    def test_retired_modes_explain_the_migration(self) -> None:
        hints = {
            "on": "defensa propia por reglas se retiró",
            "own": "defensa propia por reglas se retiró",
            "own-llm-guard": "usa llm-guard-default o prompt-guard-2",
            "own-prompt-guard": "usa llm-guard-default o prompt-guard-2",
            "llm-guard": "ahora se llama llm-guard-default",
            "prompt-guard": "ahora es prompt-guard-2",
        }
        options = "Opciones válidas: off, llm-guard-default, llm-guard-tuned, prompt-guard-2"
        for name, hint in hints.items():
            for origin, overrides, environ in (
                ("cli", {"defense": name}, {}),
                ("env", {}, {"PTH_DEFENSE": name}),
            ):
                with self.subTest(name=name, origin=origin):
                    with self.assertRaises(ConfigError) as raised:
                        load_config(cli_overrides=overrides, environ=environ)
                    message = str(raised.exception)
                    self.assertIn(f"(origen: {origin}): {name!r}", message)
                    self.assertIn(hint.casefold(), message.casefold())
                    self.assertIn(options, message)

    def test_invalid_lists_are_rejected(self) -> None:
        for text in ("", "off,", "off,off", "own,on", "off,maybe", "off,llm-guard"):
            with self.subTest(text=text):
                with self.assertRaises(ConfigError):
                    parse_defense_modes(text)

    def test_invalid_mode_lists_the_options(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            load_config(cli_overrides={}, environ={"PTH_DEFENSE": "maybe"})
        message = str(raised.exception)
        self.assertIn("off, llm-guard-default, llm-guard-tuned, prompt-guard-2", message)
        self.assertIn("env", message)


class TemperatureTest(unittest.TestCase):
    def test_mock_uses_its_fixed_temperature(self) -> None:
        config = load_config(cli_overrides={}, environ={})
        self.assertEqual(config.temperature, MOCK_TEMPERATURE)

    def test_other_providers_use_their_section(self) -> None:
        tmp_dir = make_temp_dir(self)
        extra = "\n".join(
            [
                "[providers.ollama]",
                "temperature = 0.3",
                "[providers.cloud]",
                "temperature = 0.7",
            ]
        )
        config_file = write_temp_config(tmp_dir, extra=extra)
        ollama = load_config(
            cli_overrides={"config": str(config_file), "provider": "ollama"},
            environ={},
        )
        cloud = load_config(
            cli_overrides={"config": str(config_file), "provider": "cloud"},
            environ={},
        )
        self.assertEqual(ollama.temperature, 0.3)
        self.assertEqual(cloud.temperature, 0.7)


class OllamaOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)
        extra = '[providers.ollama]\nthink = true\nformat = "schema"'
        self.config_file = write_temp_config(self.tmp_dir, extra=extra)

    def test_defaults_are_qwen_without_thinking_and_json_format(self) -> None:
        config = load_config(cli_overrides={}, environ={})
        self.assertEqual(config.ollama.model, "qwen3.5:4b")
        self.assertIs(config.ollama.think, False)
        self.assertIs(config.ollama.output_format, OllamaFormat.JSON)
        self.assertIs(config.provider, ProviderName.MOCK)

    def test_file_sets_think_and_format(self) -> None:
        config = load_config(cli_overrides={"config": str(self.config_file)}, environ={})
        self.assertIs(config.ollama.think, True)
        self.assertIs(config.ollama.output_format, OllamaFormat.SCHEMA)
        self.assertEqual(config.sources["ollama.think"], ConfigSource.FILE)
        self.assertEqual(config.sources["ollama.format"], ConfigSource.FILE)

    def test_environment_overrides_think_and_format(self) -> None:
        environ = {"PTH_OLLAMA_THINK": "False", "PTH_OLLAMA_FORMAT": "none"}
        cli = {"config": str(self.config_file)}
        config = load_config(cli_overrides=cli, environ=environ)
        self.assertIs(config.ollama.think, False)
        self.assertIs(config.ollama.output_format, OllamaFormat.NONE)
        self.assertEqual(config.sources["ollama.think"], ConfigSource.ENV)
        self.assertEqual(config.sources["ollama.format"], ConfigSource.ENV)

    def test_both_values_are_written_to_the_record(self) -> None:
        record = load_config(cli_overrides={"config": str(self.config_file)}, environ={})
        ollama = record.to_record()["ollama"]
        self.assertIsInstance(ollama, dict)
        if isinstance(ollama, dict):
            self.assertEqual((ollama["think"], ollama["format"]), (True, "schema"))

    def test_invalid_think_or_format_is_rejected(self) -> None:
        for environ in ({"PTH_OLLAMA_THINK": "quizas"}, {"PTH_OLLAMA_FORMAT": "yaml"}):
            with self.subTest(environ=environ):
                with self.assertRaises(ConfigError):
                    load_config(cli_overrides={}, environ=environ)
        config_file = write_temp_config(make_temp_dir(self), extra="[providers.ollama]\nthink = 1")
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"config": str(config_file)}, environ={})


class InvalidConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = make_temp_dir(self)

    def test_unknown_provider_lists_the_valid_options(self) -> None:
        with self.assertRaises(ConfigError) as raised:
            load_config(cli_overrides={}, environ={"PTH_PROVIDER": "gpt"})
        self.assertIn("mock, ollama, cloud", str(raised.exception))
        self.assertIn("env", str(raised.exception))

    def test_unknown_defense_mode_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"defense": "maybe"}, environ={})

    def test_unknown_key_in_file_is_rejected(self) -> None:
        config_file = write_temp_config(self.tmp_dir, harness_lines=['provder = "mock"'])
        with self.assertRaises(ConfigError) as raised:
            load_config(cli_overrides={"config": str(config_file)}, environ={})
        self.assertIn("harness.provder", str(raised.exception))

    def test_removed_policy_keys_explain_the_team_context(self) -> None:
        keys = ("allowed_email_domains", "allowed_onedrive_root", "allowed_jira_projects")
        for section in ("defense.policy", "system_policy"):
            for key in keys:
                with self.subTest(section=section, key=key):
                    extra = f'[{section}]\n{key} = "x"'
                    config_file = write_temp_config(make_temp_dir(self), extra=extra)
                    with self.assertRaises(ConfigError) as raised:
                        load_config(cli_overrides={"config": str(config_file)}, environ={})
                    message = str(raised.exception)
                    self.assertIn(f"{section}.{key} ya no existe", message)
                    self.assertIn("team_context.json", message)

    def test_removed_sections_explain_the_migration(self) -> None:
        hints = {
            "[defense.policy]\nmax_content_chars = 1500": "ahora es [system_policy]",
            "[defense.llm_guard]\nthreshold = 0.92": "[defense.llm_guard_tuned]",
            "[defense.prompt_guard]\nthreshold = 0.5": "ahora es [defense.prompt_guard_2]",
        }
        for extra, hint in hints.items():
            with self.subTest(extra=extra):
                config_file = write_temp_config(make_temp_dir(self), extra=extra)
                with self.assertRaises(ConfigError) as raised:
                    load_config(cli_overrides={"config": str(config_file)}, environ={})
                self.assertIn(hint, str(raised.exception))

    def test_unknown_table_is_rejected(self) -> None:
        config_file = write_temp_config(self.tmp_dir, extra="[providers.openai]\nmodel = 'x'")
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"config": str(config_file)}, environ={})

    def test_missing_config_file_is_a_config_error(self) -> None:
        missing = self.tmp_dir / "missing.toml"
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"config": str(missing)}, environ={})

    def test_malformed_toml_is_a_config_error(self) -> None:
        broken = self.tmp_dir / "broken.toml"
        broken.write_text("[harness\nprovider = ", encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"config": str(broken)}, environ={})

    def test_wrong_value_types_are_rejected(self) -> None:
        invalid_extras = [
            "[system_policy]\nmax_content_chars = 0",
            "[system_policy]\nmax_content_chars = true",
            "[providers.ollama]\ntimeout_seconds = -1",
            "[providers.cloud]\ntemperature = -0.5",
            '[providers.cloud]\nthinking_level = "maximal"',
            "[defense.llm_guard_tuned]\nthreshold = 1",
            "[defense.llm_guard_tuned]\nthreshold = 0",
            '[defense.llm_guard_tuned]\nmatch_type = "sentence"',
            "[defense.prompt_guard_2]\nthreshold = 0",
            "[defense.prompt_guard_2]\nthreshold = 1",
            "[defense.prompt_guard_2]\nthreshold = 1.5",
            '[defense.prompt_guard_2]\nthreshold = "x"',
            "[defense.prompt_guard_2]\nthreshold = true",
        ]
        for extra in invalid_extras:
            with self.subTest(extra=extra):
                config_file = write_temp_config(make_temp_dir(self), extra=extra)
                with self.assertRaises(ConfigError):
                    load_config(cli_overrides={"config": str(config_file)}, environ={})

    def test_model_key_is_not_configurable(self) -> None:
        for section in ("defense.llm_guard_tuned", "defense.prompt_guard_2"):
            for key in ("model", "revision", "device"):
                with self.subTest(section=section, key=key):
                    extra = f'[{section}]\n{key} = "x"'
                    config_file = write_temp_config(make_temp_dir(self), extra=extra)
                    with self.assertRaises(ConfigError) as raised:
                        load_config(cli_overrides={"config": str(config_file)}, environ={})
                    message = str(raised.exception)
                    self.assertIn(f"Clave desconocida en {config_file.resolve()}", message)
                    self.assertIn(f"{section}.{key}", str(raised.exception))

    def test_strip_speaker_must_be_boolean(self) -> None:
        for value in ("1", '"quizas"', "0.5"):
            with self.subTest(value=value):
                extra = f"[defense.prompt_guard_2]\nstrip_speaker = {value}"
                config_file = write_temp_config(make_temp_dir(self), extra=extra)
                with self.assertRaises(ConfigError) as raised:
                    load_config(cli_overrides={"config": str(config_file)}, environ={})
                self.assertIn("prompt_guard_2.strip_speaker", str(raised.exception))

    def test_unknown_cli_override_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(cli_overrides={"model": "x"}, environ={})


class CloudOptionsTest(unittest.TestCase):
    def test_defaults_follow_the_gemini_3_guidance(self) -> None:
        cloud = load_config(cli_overrides={}, environ={}).cloud
        self.assertEqual(cloud.model, "gemini-3.8-flash")
        self.assertEqual(cloud.base_url, "https://generativelanguage.googleapis.com/v1beta")
        self.assertEqual(cloud.temperature, 1.0)
        self.assertIs(cloud.thinking_level, CloudThinkingLevel.LOW)
        self.assertEqual(cloud.timeout_seconds, 120.0)

    def test_environment_overrides_cloud_options(self) -> None:
        environ = {
            "PTH_CLOUD_BASE_URL": "https://example.com/v1beta",
            "PTH_CLOUD_TEMPERATURE": "0",
            "PTH_CLOUD_THINKING_LEVEL": "default",
        }
        config = load_config(cli_overrides={"provider": "cloud"}, environ=environ)
        self.assertEqual(config.cloud.base_url, "https://example.com/v1beta")
        self.assertEqual(config.temperature, 0.0)
        self.assertIs(config.cloud.thinking_level, CloudThinkingLevel.DEFAULT)
        for key in ("cloud.base_url", "cloud.temperature", "cloud.thinking_level"):
            self.assertEqual(config.sources[key], ConfigSource.ENV)

    def test_invalid_cloud_temperature_from_the_environment_is_rejected(self) -> None:
        for value in ("caliente", "-1", "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(ConfigError):
                    load_config(cli_overrides={}, environ={"PTH_CLOUD_TEMPERATURE": value})

    def test_cloud_and_scanner_options_are_recorded(self) -> None:
        record = load_config(cli_overrides={}, environ={}).to_record()
        cloud = record["cloud"]
        self.assertIsInstance(cloud, dict)
        if isinstance(cloud, dict):
            self.assertEqual(cloud["thinking_level"], "low")
            self.assertEqual(cloud["base_url"], "https://generativelanguage.googleapis.com/v1beta")
            self.assertEqual(cloud["temperature"], 1.0)
        baseline = {
            "model": "protectai/deberta-v3-base-prompt-injection-v2",
            "threshold": 0.92,
            "match_type": "full",
            "strip_speaker": True,
        }
        self.assertEqual(record["llm_guard_default"], baseline)
        prompt_guard_2 = record["prompt_guard_2"]
        self.assertIsInstance(prompt_guard_2, dict)
        if isinstance(prompt_guard_2, dict):
            self.assertEqual(prompt_guard_2["model"], "meta-llama/Llama-Prompt-Guard-2-86M")
        self.assertNotIn("policy", record)
        self.assertNotIn("llm_guard", record)
        self.assertEqual(record["calibration_dir"], "calibration")
        self.assertEqual(record["team_context_file"], "team_context.json")


class ScannerOptionsTest(unittest.TestCase):
    def test_scanner_settings_per_mode(self) -> None:
        extra = "\n".join(
            [
                "[defense.llm_guard_tuned]",
                "threshold = 0.5",
                'match_type = "chunks"',
                "strip_speaker = false",
                "[defense.prompt_guard_2]",
                "threshold = 0.2",
                'match_type = "full"',
                'strip_speaker = "true"',
            ],
        )
        config_file = write_temp_config(make_temp_dir(self), extra=extra)
        config = load_config(cli_overrides={"config": str(config_file)}, environ={})
        self.assertIsNone(config.scanner_settings(DefenseMode.OFF))
        self.assertEqual(config.scanner_settings(DefenseMode.LLM_GUARD_DEFAULT), BASELINE_SCANNER)
        self.assertEqual(
            config.scanner_settings(DefenseMode.LLM_GUARD_TUNED),
            ScannerSettings(ScannerModel.PROTECTAI_V2, 0.5, LlmGuardMatchType.CHUNKS, False),
        )
        self.assertEqual(
            config.scanner_settings(DefenseMode.PROMPT_GUARD_2),
            ScannerSettings(ScannerModel.PROMPT_GUARD_2, 0.2, LlmGuardMatchType.FULL, True),
        )

    def test_baseline_is_the_scanner_of_e12_and_e18(self) -> None:
        expected = ScannerSettings(
            ScannerModel.PROTECTAI_V2,
            0.92,
            LlmGuardMatchType.FULL,
            strip_speaker=True,
        )
        self.assertEqual(BASELINE_SCANNER, expected)

    def test_scanner_sections_from_the_file_are_recorded_with_their_source(self) -> None:
        extra = "[defense.prompt_guard_2]\nthreshold = 0.7"
        config_file = write_temp_config(make_temp_dir(self), extra=extra)
        config = load_config(cli_overrides={"config": str(config_file)}, environ={})
        self.assertEqual(config.prompt_guard_2.threshold, 0.7)
        self.assertEqual(config.sources["prompt_guard_2.threshold"], ConfigSource.FILE)
        self.assertEqual(config.sources["prompt_guard_2.match_type"], ConfigSource.DEFAULT)
        record = config.to_record()
        recorded = record["prompt_guard_2"]
        self.assertIsInstance(recorded, dict)
        if isinstance(recorded, dict):
            self.assertEqual(recorded["threshold"], 0.7)
        sources = record["sources"]
        self.assertIsInstance(sources, dict)
        if isinstance(sources, dict):
            self.assertEqual(sources["prompt_guard_2.threshold"], "file")


class RecordTest(unittest.TestCase):
    def test_record_uses_relative_paths_with_the_default_config(self) -> None:
        record = load_config(cli_overrides={}, environ={}).to_record()
        self.assertEqual(record["cases_dir"], "cases")
        self.assertEqual(record["inputs_dir"], "inputs")
        self.assertEqual(record["system_prompt_file"], "prompts/system_prompt.es.txt")
        self.assertEqual(record["config_file"], "config.toml")

    def test_record_names_the_key_variable_but_never_its_value(self) -> None:
        environ = {"PTH_CLOUD_API_KEY": "synthetic-value-that-must-not-leak"}
        config = load_config(cli_overrides={"provider": "cloud"}, environ=environ)
        record = config.to_record()
        self.assertNotIn("synthetic-value-that-must-not-leak", repr(record))
        cloud = record["cloud"]
        self.assertIsInstance(cloud, dict)
        if isinstance(cloud, dict):
            self.assertEqual(cloud["api_key_env"], "PTH_CLOUD_API_KEY")

    def test_record_lists_the_source_of_each_value(self) -> None:
        record = load_config(cli_overrides={"defense": "llm-guard-default"}, environ={}).to_record()
        sources = record["sources"]
        self.assertIsInstance(sources, dict)
        if isinstance(sources, dict):
            self.assertEqual(sources["defense"], "cli")
            self.assertEqual(sources["provider"], "file")
            self.assertEqual(sources["config_file"], "default")


if __name__ == "__main__":
    unittest.main()
