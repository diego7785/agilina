"""LiveKit job: what the worker does once per ceremony, in its own subprocess.

This is the driving adapter of the worker. It receives its collaborators from
the composition root (``main.py``) and never imports the infrastructure layer.

The room name says which tenant and ceremony it is (``parse_room_name``). Agilina
publishes its state in the ``agilina.state`` participant attribute, waits for the first
person and greets once per room. Without the context there is no facilitation: Agilina
says so in the room and the machine is never created (CA5).

On standby Agilina is subscribed to the audio but never calls the transcriber: nothing
said before the ceremony starts is transcribed, stored or logged.

What Agilina could not say out loud is published in the ``agilina.text`` attribute so the
room shows it as text, and the ceremony goes on (AGI-69). It is cleared once the voice
is heard again, so the room never shows an old sentence.
"""

import logging

from livekit.agents import AutoSubscribe, JobContext

from agilina_agent.application.errors import ContextUnavailableError, SpeechUnavailableError
from agilina_agent.application.ports import AgilinaApi, SpeechSynthesizer, Transcriber
from agilina_agent.domain.facilitation import FacilitationMachine
from agilina_shared.contract import CeremonyContext
from agilina_shared.enums import Language
from agilina_shared.i18n import render_text
from agilina_shared.room_name import parse_room_name

logger = logging.getLogger(__name__)

# Participant attribute the room screen reads: a contract between the agent and the web.
STATE_ATTRIBUTE = "agilina.state"
# Same contract: the last sentence Agilina could not say, or empty.
TEXT_ATTRIBUTE = "agilina.text"


class RoomJob:
    def __init__(
        self,
        api: AgilinaApi,
        synthesizer: SpeechSynthesizer,
        transcriber: Transcriber,
        default_language: Language,
    ) -> None:
        self._api = api
        self._synthesizer = synthesizer
        # Not called on standby: it only listens once someone starts the daily.
        self._transcriber = transcriber
        self._default_language = default_language
        # The facilitation of this room, for AGI-62; None while there is no context.
        self.machine: FacilitationMachine | None = None
        self._showing_text = False

    async def run(self, ctx: JobContext) -> None:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        logger.info("Agilina joined room %s", ctx.room.name)

        context = await self._context_of(ctx.room.name)
        state = "no_facilitation" if context is None else "standby"
        await ctx.room.local_participant.set_attributes({STATE_ATTRIBUTE: state})
        if context is not None:
            self.machine = FacilitationMachine(context)

        # Awaited once, not on every participant_connected: one greeting per room.
        await ctx.wait_for_participant()
        if context is None:
            text = render_text("context_unavailable", self._default_language)
            await self.say(ctx, text, self._default_language)
            return

        text = render_text(
            "standby_greeting",
            context.language,
            day=context.sprint_day,
            total=context.sprint_total_days,
        )
        await self.say(ctx, text, context.language)

    async def say(self, ctx: JobContext, text: str, language: Language) -> None:
        """Says a sentence in the room or, if the voice does not come out, shows it as text."""
        try:
            await self._synthesizer.synthesize(text, language)
        except SpeechUnavailableError:
            await ctx.room.local_participant.set_attributes({TEXT_ATTRIBUTE: text})
            self._showing_text = True
            return
        if self._showing_text:
            await ctx.room.local_participant.set_attributes({TEXT_ATTRIBUTE: ""})
            self._showing_text = False

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
