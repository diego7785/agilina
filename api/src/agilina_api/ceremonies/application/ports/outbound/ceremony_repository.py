"""Write side of the ceremonies: the ``Ceremony`` aggregate and the result it receives."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_shared import CeremonyResult


class CeremonyRepository(Protocol):
    """In ``application`` and not in ``domain``: storing the result takes the shared contract,
    which the domain must not know (it imports Pydantic)."""

    async def lock(self, ceremony_id: UUID) -> Ceremony | None:
        """The ceremony with the digest of its result, or ``None``; its row stays **locked**
        until the transaction ends, so two deliveries of the same ceremony never interleave.

        Keyed by the ceremony, like ``CeremonyQueries.ceremony_of``: the worker knows only the
        ceremony, and this is where its team is found out.
        """
        ...

    async def add_result(
        self, ceremony: Ceremony, result: CeremonyResult, *, received_at: datetime
    ) -> None:
        """Store the result the ceremony just received (``Ceremony.receive_result``), with its
        segments and events in the order they came. Another result stored at the same time
        raises ``ResultAlreadyReceivedError``."""
        ...
