from agilina_api.shared.presentation.http.api_error.api_error import ApiError


class SharedErrors:
    TENANT_REQUIRED = ApiError(400, "tenant_required", "The request does not name a tenant.")
    # One answer for a tenant that does not exist, one that is suspended and a name that is
    # not valid: a different one would let anybody list the tenants.
    TENANT_NOT_FOUND = ApiError(404, "tenant_not_found", "The tenant does not exist.")
    NOT_AUTHENTICATED = ApiError(
        401,
        "not_authenticated",
        "A valid access token is required.",
        {"WWW-Authenticate": "Bearer"},
    )
    # A valid token of someone who is not an active user of the organization: the person is
    # signed in, so the web must not send them to sign in again.
    ACCOUNT_NOT_ACTIVE = ApiError(
        403, "account_not_active", "The account is not active in this organization."
    )
    # The same answer whether the team is someone else's, the user was removed from it or
    # it does not exist: a 404 for the last one would let anybody enumerate teams.
    NOT_A_TEAM_MEMBER = ApiError(403, "not_a_team_member", "The user is not a member of the team.")
    NOT_A_TEAM_ADMIN = ApiError(403, "not_a_team_admin", "The user is not an admin of the team.")
    # Teams and identity (an invitation to a team) both answer it.
    TEAM_NOT_FOUND = ApiError(404, "team_not_found", "The team does not exist.")
    VALIDATION = ApiError(422, "validation_error", "The request is not valid.")
    NOT_FOUND = ApiError(404, "not_found", "The resource does not exist.")
    METHOD_NOT_ALLOWED = ApiError(405, "method_not_allowed", "The method is not allowed here.")
    MAIL_UNAVAILABLE = ApiError(502, "mail_unavailable", "The email could not be sent.")
    NOT_IMPLEMENTED = ApiError(501, "not_implemented", "The operation is not implemented yet.")
    INTERNAL = ApiError(500, "internal_error", "Something went wrong on our side.")
