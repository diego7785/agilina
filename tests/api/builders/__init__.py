"""Data Builders: they put together the objects the tests need.

Every builder starts from valid, fixed defaults, changes one thing per ``with_…`` call
(each call returns a new builder, so a shared baseline is never altered) and builds the
object through the domain's own rules. A state like "used" or "expired" is reached by
behavior (``Invitation.accept``), never by writing private fields.
"""

from tests.api.builders.access_token import (
    AUDIENCE,
    ISSUER,
    SUBJECT,
    AccessTokenBuilder,
    SigningKey,
    signing_key,
)
from tests.api.builders.ceremony import CeremonyBuilder, RosterBuilder
from tests.api.builders.contacts import ContactBuilder, TeamContactsBuilder
from tests.api.builders.defaults import DAILY_LOCAL_TIME, DAILY_TIME, NOW, PASSWORD, TOKEN
from tests.api.builders.email_message import EmailMessageBuilder
from tests.api.builders.identifiers import next_id, reset_ids
from tests.api.builders.identity_commands import (
    ActivateAccountBuilder,
    InviteToTeamBuilder,
    IssueInvitationBuilder,
    RequestNewInvitationBuilder,
)
from tests.api.builders.invitation import InvitationBuilder
from tests.api.builders.sprint import SprintBuilder
from tests.api.builders.team import TeamBuilder
from tests.api.builders.team_commands import (
    ChangeMemberRoleBuilder,
    ReconfigureSprintBuilder,
    RemoveMemberBuilder,
    StartSprintBuilder,
)
from tests.api.builders.tenant import TenantBuilder
from tests.api.builders.user import AppUserBuilder

__all__ = [
    "AUDIENCE",
    "DAILY_LOCAL_TIME",
    "DAILY_TIME",
    "ISSUER",
    "NOW",
    "PASSWORD",
    "SUBJECT",
    "TOKEN",
    "AccessTokenBuilder",
    "ActivateAccountBuilder",
    "AppUserBuilder",
    "CeremonyBuilder",
    "ChangeMemberRoleBuilder",
    "ContactBuilder",
    "EmailMessageBuilder",
    "InvitationBuilder",
    "InviteToTeamBuilder",
    "SigningKey",
    "IssueInvitationBuilder",
    "ReconfigureSprintBuilder",
    "RemoveMemberBuilder",
    "RequestNewInvitationBuilder",
    "RosterBuilder",
    "SprintBuilder",
    "StartSprintBuilder",
    "TeamBuilder",
    "TeamContactsBuilder",
    "TenantBuilder",
    "next_id",
    "reset_ids",
    "signing_key",
]
