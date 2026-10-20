from agilina_api.shared_kernel import DomainError


class NotADailyParticipantError(DomainError):
    """Whoever asks to join is not among the participants of the active sprint's daily, the
    team's admin included (AGI-59)."""
