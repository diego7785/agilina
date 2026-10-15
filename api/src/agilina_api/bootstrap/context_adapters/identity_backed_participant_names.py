from collections.abc import Collection
from uuid import UUID

from agilina_api.ceremonies.application.ports.outbound import ParticipantNames
from agilina_api.identity.infrastructure.persistence.user_contacts import SqlUserContacts


class IdentityBackedParticipantNames(ParticipantNames):
    """The names of a ceremony's participants, for ceremonies, from identity's accounts."""

    def __init__(self, user_contacts: SqlUserContacts) -> None:
        self._user_contacts = user_contacts

    async def names_of(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        contacts = await self._user_contacts.contacts_by_id(user_ids)
        return {user_id: contact.full_name for user_id, contact in contacts.items()}
