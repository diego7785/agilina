"""Worker entry point and composition root.

    make agent     → registers the worker in LiveKit and waits for jobs

The worker opens an outbound connection to LiveKit and registers. When a
ceremony room is created, LiveKit offers the job over that connection and this
module launches the subprocess that joins the room as one more participant.

What is here is the skeleton that shows the life cycle: join the room, ask the
API for the ceremony context, announce itself and wait. Before registering, the
worker resends once the results kept on disk that the API never accepted. Full
facilitation arrives with the Release 1 and 2 stories; the logic that already
exists lives in ``agilina_agent.domain.facilitation`` and is tested without a
room or audio.
"""

import asyncio

import httpx
from livekit.agents import JobContext, WorkerOptions, cli

from agilina_agent.infrastructure.http_agilina_api import REQUEST_TIMEOUT, HttpAgilinaApi
from agilina_agent.infrastructure.logging_setup import configure_logging, get_logger
from agilina_agent.infrastructure.pending_results import PendingResults
from agilina_agent.infrastructure.settings import Settings, get_settings
from agilina_agent.infrastructure.speech_synthesizers import RecordingSynthesizer
from agilina_agent.infrastructure.worker_tokens import KeycloakWorkerTokens
from agilina_agent.presentation.room_job import RoomJob

logger = get_logger(__name__)


def agilina_api(settings: Settings) -> HttpAgilinaApi:
    client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
    tokens = KeycloakWorkerTokens(
        keycloak_url=settings.keycloak_url,
        realm_prefix=settings.tenant_realm_prefix,
        client_id=settings.keycloak_worker_client,
        secret_of=settings.worker_secret,
        client=client,
    )
    return HttpAgilinaApi(
        base_url=settings.api_public_url,
        token_for=tokens.token_for,
        pending=PendingResults(settings.agent_pending_dir),
        client=client,
    )


async def resend_pending(settings: Settings) -> None:
    api = agilina_api(settings)
    try:
        await api.resend_pending()
    finally:
        await api.close()


async def entrypoint(ctx: JobContext) -> None:
    """Runs once per ceremony, in its own subprocess: wires the job here."""
    settings = get_settings()
    configure_logging(settings.log_level)

    job = RoomJob(
        api=agilina_api(settings),
        synthesizer=RecordingSynthesizer(),
        default_language=settings.default_language,
    )
    await job.run(ctx)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    asyncio.run(resend_pending(settings))
    logger.info("Registering the worker in %s", settings.livekit_url or "(not configured)")

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )


__all__ = ["entrypoint", "run"]

if __name__ == "__main__":
    run()
