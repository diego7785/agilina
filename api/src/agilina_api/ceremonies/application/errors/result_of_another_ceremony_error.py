from agilina_api.shared_kernel import DomainError


class ResultOfAnotherCeremonyError(DomainError):
    """The result names another ceremony than the one it is delivered to."""
