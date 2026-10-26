"""The composition root: the adapter is built without connecting, the startup resend
reads the configured folder and leaves there what it could not deliver, and the worker
registers without a name so LiveKit dispatches every room to it."""

from pathlib import Path

import pytest
from livekit.agents import WorkerOptions
from livekit.protocol.models import TrackSource

from agilina_agent import main
from agilina_agent.infrastructure.http_agilina_api import HttpAgilinaApi
from agilina_agent.infrastructure.pending_results import PendingResults
from agilina_agent.infrastructure.settings import Settings
from agilina_agent.main import agilina_api, entrypoint, resend_pending, worker_options
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


def test_the_worker_registers_for_automatic_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered: list[WorkerOptions] = []
    monkeypatch.setattr(main, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main.cli, "run_app", registered.append)

    main.run()

    [options] = registered
    # LiveKit dispatches every new room only to workers registered without a name.
    assert options.agent_name == ""
    assert options.entrypoint_fnc is entrypoint


def test_the_agent_can_listen_speak_and_publish_its_state_but_not_data(tmp_path: Path) -> None:
    permissions = worker_options(_settings(tmp_path)).permissions

    assert permissions.can_subscribe
    assert permissions.can_publish
    # Only its voice: no camera or screen share.
    assert permissions.can_publish_sources == [TrackSource.MICROPHONE]
    assert permissions.can_update_metadata
    assert not permissions.can_publish_data
    # Agilina must show up in the participant list.
    assert not permissions.hidden
