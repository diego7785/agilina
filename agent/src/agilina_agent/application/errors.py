"""Errors of the worker ports."""


class ContextUnavailableError(Exception):
    """The API did not hand over the ceremony context: without it there is no facilitation."""
