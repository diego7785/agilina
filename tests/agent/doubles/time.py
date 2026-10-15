"""Time doubles: waits are recorded instead of slept, and the clock moves when told."""

from collections.abc import Callable


class RecordedSleep:
    """Stands in for ``asyncio.sleep``: the test reads the waits instead of living them."""

    def __init__(self, during_wait: Callable[[], None] | None = None) -> None:
        self.waits: list[float] = []
        self._during_wait = during_wait

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
        if self._during_wait is not None:
            self._during_wait()


class FakeMonotonicClock:
    """Stands in for ``time.monotonic``."""

    def __init__(self, now: float = 1000.0) -> None:
        self.current = now

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds
