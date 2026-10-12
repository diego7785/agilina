"""Who is calling and what they may reach: the user of Agilina behind the bearer token of
a request, and their membership in the team the request is about.

Every context needs both and none of them owns them, so the ports live here. Validating the
token is the login story's job (HU-03); until then the composition root wires an adapter
that turns every token away (``bootstrap.authentication``).
"""

from agilina_api.shared.application.access.account_not_active_error import AccountNotActiveError
from agilina_api.shared.application.access.authenticated_users import AuthenticatedUsers
from agilina_api.shared.application.access.membership_ref import MembershipRef
from agilina_api.shared.application.access.not_a_team_admin_error import NotATeamAdminError
from agilina_api.shared.application.access.not_a_team_member_error import NotATeamMemberError
from agilina_api.shared.application.access.not_authenticated_error import NotAuthenticatedError
from agilina_api.shared.application.access.team_access import TeamAccess
from agilina_api.shared.application.access.team_context import TeamContext

__all__ = [
    "AccountNotActiveError",
    "AuthenticatedUsers",
    "MembershipRef",
    "NotATeamAdminError",
    "NotATeamMemberError",
    "NotAuthenticatedError",
    "TeamAccess",
    "TeamContext",
]
