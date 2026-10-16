"""Without the context there is no facilitation: Agilina says so in the room (CA5)."""

import pytest
from livekit.agents import AutoSubscribe

from agilina_agent.infrastructure.speech_synthesizers import RecordingSynthesizer
from agilina_agent.presentation.room_job import RoomJob
from agilina_shared import room_name_for
from agilina_shared.enums import Language
from agilina_shared.i18n import render_text
from tests.agent.doubles import FakeAgilinaApi, FakeJobContext
from tests.shared.builders import TENANT, CeremonyContextBuilder


@pytest.mark.parametrize("language", [Language.ES, Language.EN])
async def test_without_the_context_agilina_announces_it_and_does_not_facilitate(
    language: Language,
) -> None:
    ceremony_id = CeremonyContextBuilder().build().ceremony_id
    api = FakeAgilinaApi(context=None)
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, default_language=language)

    await job.run(FakeJobContext(room_name_for(TENANT, ceremony_id)))

    assert api.asked == [(TENANT, ceremony_id)]
    assert synthesizer.spoken == [(language, render_text("context_unavailable", language))]
    assert job.machine is None


@pytest.mark.parametrize("room_name", ["lobby", "acme-not-a-ceremony", ""])
async def test_a_room_not_named_after_a_ceremony_is_announced_without_asking_the_api(
    room_name: str,
) -> None:
    api = FakeAgilinaApi(context=CeremonyContextBuilder().build())
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, default_language=Language.ES)

    await job.run(FakeJobContext(room_name))

    assert api.asked == []
    assert synthesizer.spoken == [(Language.ES, render_text("context_unavailable", Language.ES))]
    assert job.machine is None


async def test_with_the_context_the_facilitation_is_created_for_that_ceremony() -> None:
    context = CeremonyContextBuilder().for_tenant("ecomoda").build()
    api = FakeAgilinaApi(context=context)
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, default_language=Language.ES)
    ctx = FakeJobContext(context.room)

    await job.run(ctx)

    assert api.asked == [("ecomoda", context.ceremony_id)]
    assert job.machine is not None
    assert job.machine.context == context
    assert ctx.subscribed == AutoSubscribe.AUDIO_ONLY
    assert render_text("context_unavailable", Language.ES) not in [
        text for _, text in synthesizer.spoken
    ]
