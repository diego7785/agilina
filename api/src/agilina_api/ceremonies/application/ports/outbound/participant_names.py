"""Port to the identity context: how the participants of a ceremony are called."""

from collections.abc import Collection
from typing import Protocol
from uuid import UUID


class ParticipantNames(Protocol):
    """Ceremonies cannot import identity (AD-21), which owns people's names, so it asks for
    them through this port; the composition root implements it."""

    async def names_of(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        """The full name of each of those users, by id, whether or not their account is
        active; a user without an account is left out."""
        ...
