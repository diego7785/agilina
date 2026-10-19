"""Dependency providers declared by the ceremonies presentation layer.

The composition root overrides them with the real handlers, so this layer never imports
the infrastructure one.
"""

from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.application.commands.join_current_daily import (
    JoinCurrentDailyHandler,
)
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContextHandler,
)


def get_get_ceremony_context_handler() -> GetCeremonyContextHandler:
    raise NotImplementedError("Wired by the composition root")


def get_deliver_ceremony_result_handler() -> DeliverCeremonyResultHandler:
    raise NotImplementedError("Wired by the composition root")


def get_join_current_daily_handler() -> JoinCurrentDailyHandler:
    raise NotImplementedError("Wired by the composition root")
