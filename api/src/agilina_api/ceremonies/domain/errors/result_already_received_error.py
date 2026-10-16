from agilina_api.shared_kernel import DomainError


class ResultAlreadyReceivedError(DomainError):
    """The ceremony already has another result: a ceremony is closed once (AGI-64)."""
