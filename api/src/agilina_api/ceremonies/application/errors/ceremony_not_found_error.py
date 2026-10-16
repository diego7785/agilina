from agilina_api.shared_kernel import DomainError


class CeremonyNotFoundError(DomainError):
    """No ceremony has that id, or its sprint is no longer the team's active one."""
