"""Common configuration of the tests of the shared package."""

import pytest

from tests.shared.builders import reset_ids


@pytest.fixture(autouse=True)
def fresh_identifiers() -> None:
    """Every test counts its identifiers from 1: a failure is reproducible."""
    reset_ids()
