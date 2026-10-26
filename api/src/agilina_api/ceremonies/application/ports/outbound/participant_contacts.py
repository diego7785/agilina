"""Port to the identity context: how the participants of a ceremony are called and reached."""

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from agilina_api.ceremonies.application.dtos import ParticipantContact


class ParticipantContacts(Protocol):
    """Ceremonies cannot import identity (AD-21), which owns people's names and emails, so it
    asks for them through this port; the composition root implements it."""

    async def contacts_of(self, user_ids: Collection[UUID]) -> dict[UUID, ParticipantContact]:
        """The name and email of each of those users, by id, whether or not their account is
        active; a user without an account is left out."""
        ...
