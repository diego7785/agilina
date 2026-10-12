class AccountNotActiveError(Exception):
    """The access token is valid, but its subject is not an active user of this organization:
    it has no ``app_user`` or the user was disabled. Not a business rule: the interface answers
    it with a ``403``, so that the web can tell it from a token that is not valid."""
