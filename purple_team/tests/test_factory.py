"""Tests for the provider factory: the provider is chosen only by configuration."""

import unittest

from purple_team.config import load_config
from purple_team.errors import ConfigError
from purple_team.providers.cloud import CloudProvider
from purple_team.providers.factory import build_provider
from purple_team.providers.mock import MockProvider, MockScript
from purple_team.providers.ollama import OllamaProvider

SCRIPTS = {"c00": MockScript(benign_response="{}", injected_response=None, trigger=None)}


class BuildProviderTest(unittest.TestCase):
    def test_builds_each_provider_from_configuration(self) -> None:
        expected_types = {
            "mock": MockProvider,
            "ollama": OllamaProvider,
            "cloud": CloudProvider,
        }
        for name, provider_type in expected_types.items():
            with self.subTest(provider=name):
                config = load_config(cli_overrides={}, environ={"PTH_PROVIDER": name})
                provider = build_provider(config, mock_scripts=SCRIPTS, environ={})
                self.assertIsInstance(provider, provider_type)

    def test_unsupported_cloud_vendor_is_a_config_error(self) -> None:
        environ = {"PTH_PROVIDER": "cloud", "PTH_CLOUD_VENDOR": "acme"}
        config = load_config(cli_overrides={}, environ=environ)
        with self.assertRaises(ConfigError):
            build_provider(config, mock_scripts=SCRIPTS, environ=environ)


if __name__ == "__main__":
    unittest.main()
