"""LiveKit job: what the worker does once per ceremony, in its own subprocess.

This is the driving adapter of the worker. It receives its collaborators from
the composition root (``main.py``) and never imports the infrastructure layer.

The room name says which tenant and ceremony it is (``parse_room_name``). Without the
context there is no facilitation: Agilina says so in the room and the machine is never
created (CA5).
"""

import logging

from livekit.agents import AutoSubscribe, JobContext

from agilina_agent.application.errors import ContextUnavailableError
from agilina_agent.application.ports import AgilinaApi, SpeechSynthesizer
from agilina_agent.domain.facilitation import FacilitationMachine
from agilina_shared.contract import CeremonyContext
from agilina_shared.enums import Language
from agilina_shared.i18n import render_text
from agilina_shared.room_name import parse_room_name

logger = logging.getLogger(__name__)


class RoomJob:
    def __init__(
        self, api: AgilinaApi, synthesizer: SpeechSynthesizer, default_language: Language
    ) -> None:
        self._api = api
        self._synthesizer = synthesizer
        self._default_language = default_language
        # The facilitation of this room, for AGI-62; None while there is no context.
        self.machine: FacilitationMachine | None = None

    async def run(self, ctx: JobContext) -> None:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        logger.info("Agilina joined room %s", ctx.room.name)

        context = await self._context_of(ctx.room.name)
        if context is None:
            await self._synthesizer.synthesize(
                render_text("context_unavailable", self._default_language),
                self._default_language,
            )
            return

        self.machine = FacilitationMachine(context)
        # Waiting: Agilina is in the room but sends no audio to the transcription
        # service until someone starts the daily from the application.
        await self._synthesizer.synthesize(
            "Agilina is in the room and waiting.", self._default_language
        )

    async def _context_of(self, room_name: str) -> CeremonyContext | None:
        ceremony = parse_room_name(room_name)
        if ceremony is None:
            logger.error("Room %s is not named after a ceremony: no facilitation", room_name)
            return None

        tenant, ceremony_id = ceremony
        try:
            return await self._api.get_context(tenant, ceremony_id)
        except ContextUnavailableError:
            logger.error("No context for room %s: no facilitation", room_name)
            return None
