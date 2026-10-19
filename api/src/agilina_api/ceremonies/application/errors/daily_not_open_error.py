from agilina_api.shared_kernel import DomainError


class DailyNotOpenError(DomainError):
    """No occurrence of the daily has its window to join open now (``current_daily_at``)."""
