"""Dependency providers declared by the ceremonies presentation layer.

The composition root overrides them with the real handlers, so this layer never imports
the infrastructure one.
"""

from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContextHandler,
)


def get_get_ceremony_context_handler() -> GetCeremonyContextHandler:
    raise NotImplementedError("Wired by the composition root")
