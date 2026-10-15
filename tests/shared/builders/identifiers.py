"""Identifiers that are unique inside a test and the same on every run.

A random ``uuid4`` makes a failure impossible to reproduce; a counter that restarts before
each test (see ``tests/shared/conftest.py``) gives distinct, predictable values.
"""

import itertools
from uuid import UUID

_counter = itertools.count(1)


def next_id() -> UUID:
    return UUID(int=next(_counter))


def reset_ids() -> None:
    global _counter  # noqa: PLW0603 - the point of this module is a resettable sequence
    _counter = itertools.count(1)
