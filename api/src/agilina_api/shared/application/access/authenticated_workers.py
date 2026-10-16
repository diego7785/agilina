from typing import Protocol


class AuthenticatedWorkers(Protocol):
    """Tells whether the bearer token of a request belongs to the agent worker (AGI-64).

    Apart from ``AuthenticatedUsers`` because the worker is a service, not a person: it has
    no ``app_user`` and no team. The contract an adapter must keep:

    - it receives the raw token, without the ``Bearer`` prefix;
    - it validates it completely (signature, issuer, audience and expiry) before trusting
      any of its claims, so a token of another tenant's realm is not valid here;
    - it returns ``None`` when the token is not valid, ``False`` when it is valid but was
      issued to someone else (a person signed in to the web) and ``True`` when it was issued
      to the worker. A bad token is an answer, not a failure: it never raises for one.
    """

    async def is_worker(self, bearer_token: str) -> bool | None: ...
