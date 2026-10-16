"""The composition root: the adapter is built without connecting, and the startup resend
reads the configured folder and leaves there what it could not deliver."""

from pathlib import Path

import pytest

from agilina_agent.infrastructure.http_agilina_api import HttpAgilinaApi
from agilina_agent.infrastructure.pending_results import PendingResults
from agilina_agent.infrastructure.settings import Settings
from agilina_agent.main import agilina_api, resend_pending
from tests.shared.builders import TENANT, CeremonyResultBuilder

# Nothing listens on the discard port: every connection is refused at once.
NOBODY = "http://127.0.0.1:9"


def _settings(pending_dir: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        api_public_url=NOBODY,
        keycloak_url=NOBODY,
        agent_pending_dir=pending_dir,
    )


async def test_the_adapter_is_built_without_connecting(tmp_path: Path) -> None:
    api = agilina_api(_settings(tmp_path))

    assert isinstance(api, HttpAgilinaApi)
    await api.close()


async def test_what_the_startup_resend_cannot_deliver_stays_in_the_configured_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("AGILINA_TENANT_ACME_KEYCLOAK_WORKER_SECRET", "secret")
    kept = PendingResults(tmp_path)
    result = CeremonyResultBuilder().build()
    kept.save(TENANT, result)

    await resend_pending(_settings(tmp_path))

    assert kept.pending() == [(TENANT, result)]
    assert f"Pending result of ceremony {result.ceremony_id} not delivered" in caplog.text
