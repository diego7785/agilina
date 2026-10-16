class NotAWorkerError(Exception):
    """The access token is valid, but it was not issued to the agent worker, and the request
    is one only the worker may make (AGI-64). Not a business rule: the interface answers it
    with a ``403``."""
