from agilina_api.shared_kernel import DomainError


class NoActiveSprintError(DomainError):
    """The team has no active sprint, so it has no daily to join (AGI-59)."""
