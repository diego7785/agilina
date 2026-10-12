"""Keycloak implementation of the ``AuthenticatedUsers`` port (HU-03).

It keeps the contract written in ``shared.application.access``: the token is validated
completely before any claim is trusted, a bad token is an answer (``None``) and never an
exception, a valid one that belongs to nobody active raises ``AccountNotActiveError``, and
nothing about teams or roles is read from the token: only who the person is. The ``sub`` of
the token is resolved to the ``app_user`` that was created when the invitation was accepted.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.persistence.user_repository import (
    SqlAlchemyUserRepository,
)
from agilina_api.shared.application.access import AccountNotActiveError, AuthenticatedUsers

logger = logging.getLogger(__name__)


class KeycloakAuthenticatedUsers(AuthenticatedUsers):
    def __init__(
        self,
        verifier: KeycloakAccessTokenVerifier,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._verifier = verifier
        self._session_factory = session_factory

    async def user_id_for(self, bearer_token: str) -> UUID | None:
        subject = await self._verifier.verified_subject(bearer_token)
        if subject is None:
            return None
        async with self._session_factory() as session:
            user = await SqlAlchemyUserRepository(session).get_by_keycloak_subject(subject)
        if user is None:
            # A valid token of someone Keycloak knows and Agilina does not: for example an
            # account created in the console. It identifies nobody here.
            logger.info("Access token rejected: its subject has no user in Agilina")
            raise AccountNotActiveError("The token's subject has no user in Agilina")
        if not user.is_active:
            logger.info("Access token rejected: its user is not active")
            raise AccountNotActiveError("The token's user is not active")
        return user.id
