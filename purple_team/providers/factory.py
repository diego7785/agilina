"""Builds the provider chosen by configuration; building never touches the network."""

from collections.abc import Mapping
from typing import assert_never

from purple_team.config import HarnessConfig, ProviderName
from purple_team.providers.base import ModelProvider
from purple_team.providers.cloud import CloudProvider
from purple_team.providers.mock import MockProvider, MockScript
from purple_team.providers.ollama import OllamaProvider


def build_provider(
    config: HarnessConfig,
    *,
    mock_scripts: Mapping[str, MockScript],
    environ: Mapping[str, str],
) -> ModelProvider:
    """Return the adapter of ``config.provider``."""
    match config.provider:
        case ProviderName.MOCK:
            return MockProvider(mock_scripts)
        case ProviderName.OLLAMA:
            return OllamaProvider(config.ollama)
        case ProviderName.CLOUD:
            return CloudProvider(config.cloud, environ)
        case _:
            assert_never(config.provider)
