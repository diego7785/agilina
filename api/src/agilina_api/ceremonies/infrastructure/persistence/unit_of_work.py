"""Unit of work of the ceremonies commands: a transaction with the ceremony repository on the
transaction's session."""

from collections.abc import Callable
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agilina_api.ceremonies.application.ports.outbound import CeremonyRepository
from agilina_api.ceremonies.infrastructure.persistence.ceremony_repository import (
    SqlAlchemyCeremonyRepository,
)
from agilina_api.shared.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyCeremoniesUnitOfWork(SqlAlchemyUnitOfWork):
    ceremonies: CeremonyRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_factory)

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.ceremonies = SqlAlchemyCeremonyRepository(self.session)
        return self


def ceremonies_unit_of_work_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], SqlAlchemyCeremoniesUnitOfWork]:
    return lambda: SqlAlchemyCeremoniesUnitOfWork(session_factory)
