"""Error of the worker token provider."""


class WorkerTokenUnavailableError(Exception):
    """The worker cannot get a token for that tenant and retrying will not change it: the slug
    is not valid, it has no secret configured or Keycloak rejected the credentials."""
