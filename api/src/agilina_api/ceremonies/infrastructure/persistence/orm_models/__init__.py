"""ORM rows of the ceremonies context. They mirror the tables; they are *not* the entities.

No ``ForeignKey`` is declared: the database enforces the one to ``sprint`` (see the migration)
and this context's models must not know another context's tables.
"""

from agilina_api.ceremonies.infrastructure.persistence.orm_models.ceremony_row import CeremonyRow

__all__ = [
    "CeremonyRow",
]
