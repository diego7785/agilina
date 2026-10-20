from agilina_api.shared_kernel import DomainError


class DailyNotOpenError(DomainError):
    """No daily of the sprint is open to join now: ``joinable_daily_at`` gives none, or the one it
    gives has not reached ``join_opens_at`` yet."""
