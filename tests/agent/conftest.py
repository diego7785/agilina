"""Common configuration of the worker tests."""

import pytest

from agilina_agent.infrastructure.settings import get_settings
from tests.shared.builders import reset_ids


@pytest.fixture(autouse=True)
def fresh_identifiers() -> None:
    """Every test counts its identifiers from 1: a failure is reproducible."""
    reset_ids()


@pytest.fixture(autouse=True)
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
