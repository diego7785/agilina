from collections.abc import Collection
from uuid import UUID

from agilina_api.ceremonies.application.dtos import ParticipantContact
from agilina_api.ceremonies.application.ports.outbound import ParticipantContacts
from agilina_api.identity.infrastructure.persistence.user_contacts import SqlUserContacts


class IdentityBackedParticipantContacts(ParticipantContacts):
    """The names and emails of a ceremony's participants, for ceremonies, from identity's
    accounts."""

    def __init__(self, user_contacts: SqlUserContacts) -> None:
        self._user_contacts = user_contacts

    async def contacts_of(self, user_ids: Collection[UUID]) -> dict[UUID, ParticipantContact]:
        contacts = await self._user_contacts.contacts_by_id(user_ids)
        return {
            user_id: ParticipantContact(full_name=contact.full_name, email=contact.email.value)
            for user_id, contact in contacts.items()
        }
