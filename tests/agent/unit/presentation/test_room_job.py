"""Agilina publishes its state, waits for the first person and greets once per room on
standby without transcribing (CA2-CA6). Without the context there is no facilitation:
Agilina says so in the room (CA5)."""

import asyncio

import pytest
from livekit.agents import AutoSubscribe

from agilina_agent.infrastructure.speech_synthesizers import RecordingSynthesizer
from agilina_agent.presentation.room_job import STATE_ATTRIBUTE, RoomJob
from agilina_shared import room_name_for
from agilina_shared.enums import Language
from agilina_shared.i18n import render_text
from tests.agent.doubles import FakeAgilinaApi, FakeJobContext, FakeTranscriber
from tests.shared.builders import TENANT, CeremonyContextBuilder


@pytest.mark.parametrize("language", [Language.ES, Language.EN])
async def test_without_the_context_agilina_announces_it_and_does_not_facilitate(
    language: Language,
) -> None:
    ceremony_id = CeremonyContextBuilder().build().ceremony_id
    api = FakeAgilinaApi(context=None)
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, FakeTranscriber(), default_language=language)
    ctx = FakeJobContext(room_name_for(TENANT, ceremony_id))

    await job.run(ctx)

    assert api.asked == [(TENANT, ceremony_id)]
    assert synthesizer.spoken == [(language, render_text("context_unavailable", language))]
    assert job.machine is None
    assert ctx.room.local_participant.attributes == {STATE_ATTRIBUTE: "no_facilitation"}


@pytest.mark.parametrize("room_name", ["lobby", "acme-not-a-ceremony", ""])
async def test_a_room_not_named_after_a_ceremony_is_announced_without_asking_the_api(
    room_name: str,
) -> None:
    api = FakeAgilinaApi(context=CeremonyContextBuilder().build())
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, FakeTranscriber(), default_language=Language.ES)
    ctx = FakeJobContext(room_name)

    await job.run(ctx)

    assert api.asked == []
    assert synthesizer.spoken == [(Language.ES, render_text("context_unavailable", Language.ES))]
    assert job.machine is None
    assert ctx.room.local_participant.attributes == {STATE_ATTRIBUTE: "no_facilitation"}


async def test_with_the_context_the_facilitation_is_created_for_that_ceremony() -> None:
    context = CeremonyContextBuilder().for_tenant("ecomoda").build()
    api = FakeAgilinaApi(context=context)
    synthesizer = RecordingSynthesizer()
    job = RoomJob(api, synthesizer, FakeTranscriber(), default_language=Language.ES)
    ctx = FakeJobContext(context.room)

    await job.run(ctx)

    assert api.asked == [("ecomoda", context.ceremony_id)]
    assert job.machine is not None
    assert job.machine.context == context
    assert ctx.subscribed == AutoSubscribe.AUDIO_ONLY
    assert render_text("context_unavailable", Language.ES) not in [
        text for _, text in synthesizer.spoken
    ]


@pytest.mark.parametrize(
    ("team_language", "default_language"),
    [(Language.ES, Language.EN), (Language.EN, Language.ES)],
)
async def test_with_the_context_agilina_greets_once_in_the_team_language(
    team_language: Language, default_language: Language
) -> None:
    context = CeremonyContextBuilder().in_language(team_language).build()
    synthesizer = RecordingSynthesizer()
    job = RoomJob(
        FakeAgilinaApi(context=context),
        synthesizer,
        FakeTranscriber(),
        default_language=default_language,
    )

    await job.run(FakeJobContext(context.room))

    greeting = render_text(
        "standby_greeting",
        team_language,
        day=context.sprint_day,
        total=context.sprint_total_days,
    )
    assert synthesizer.spoken == [(team_language, greeting)]


async def test_with_the_context_agilina_publishes_it_is_on_standby() -> None:
    context = CeremonyContextBuilder().build()
    job = RoomJob(
        FakeAgilinaApi(context=context),
        RecordingSynthesizer(),
        FakeTranscriber(),
        default_language=Language.ES,
    )
    ctx = FakeJobContext(context.room)

    await job.run(ctx)

    assert ctx.room.local_participant.attributes == {STATE_ATTRIBUTE: "standby"}


async def test_agilina_waits_for_the_first_person_before_speaking() -> None:
    context = CeremonyContextBuilder().build()
    synthesizer = RecordingSynthesizer()
    job = RoomJob(
        FakeAgilinaApi(context=context),
        synthesizer,
        FakeTranscriber(),
        default_language=Language.ES,
    )
    ctx = FakeJobContext(context.room, nobody_yet=True)

    running = asyncio.create_task(job.run(ctx))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert not running.done()
    assert ctx.waited_for_participant == 1
    assert ctx.room.local_participant.attributes == {STATE_ATTRIBUTE: "standby"}
    assert synthesizer.spoken == []

    ctx.person_joins()
    await running

    assert ctx.waited_for_participant == 1
    assert len(synthesizer.spoken) == 1


@pytest.mark.parametrize("has_context", [True, False])
async def test_on_standby_agilina_never_calls_the_transcriber(has_context: bool) -> None:
    context = CeremonyContextBuilder().build()
    transcriber = FakeTranscriber()
    job = RoomJob(
        FakeAgilinaApi(context=context if has_context else None),
        RecordingSynthesizer(),
        transcriber,
        default_language=Language.ES,
    )

    await job.run(FakeJobContext(context.room))

    assert transcriber.transcribed == 0
    assert transcriber.availability_checks == 0
