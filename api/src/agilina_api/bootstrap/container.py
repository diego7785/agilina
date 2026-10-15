"""The composition root's object graph of one tenant: every use case wired to its real
adapters, to the tenant's own database and to the tenant's own realm (AD-29).

The API (``bootstrap.app``, through ``TenantContainers``) and the operator commands
(``make invite``) build the same graph, so they cannot drift apart.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from agilina_api.bootstrap.context_adapters import (
    IdentityBackedMemberContacts,
    IdentityBackedParticipantNames,
    TeamsBackedCeremonyRoster,
    TeamsBackedContacts,
    team_membership_factory,
)
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContextHandler,
)
from agilina_api.ceremonies.infrastructure.persistence.ceremony_queries import SqlCeremonyQueries
from agilina_api.identity.application.commands.activate_account import ActivateAccountHandler
from agilina_api.identity.application.commands.invite_to_team import InviteToTeamHandler
from agilina_api.identity.application.commands.issue_invitation import IssueInvitationHandler
from agilina_api.identity.application.commands.request_new_invitation import (
    RequestNewInvitationHandler,
)
from agilina_api.identity.application.queries.get_invitation_status import (
    GetInvitationStatusHandler,
)
from agilina_api.identity.infrastructure.keycloak.access_token_verifier import (
    KeycloakAccessTokenVerifier,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_users import (
    KeycloakAuthenticatedUsers,
)
from agilina_api.identity.infrastructure.keycloak.authenticated_workers import (
    KeycloakAuthenticatedWorkers,
)
from agilina_api.identity.infrastructure.keycloak.identity_provider import KeycloakIdentityProvider
from agilina_api.identity.infrastructure.persistence.invitation_queries import SqlInvitationQueries
from agilina_api.identity.infrastructure.persistence.unit_of_work import (
    identity_unit_of_work_factory,
)
from agilina_api.identity.infrastructure.persistence.user_contacts import SqlUserContacts
from agilina_api.identity.infrastructure.tokens import SecretsActivationTokenGenerator
from agilina_api.shared.application.access import (
    AuthenticatedUsers,
    AuthenticatedWorkers,
    TeamAccess,
)
from agilina_api.shared.application.tenancy import Tenant
from agilina_api.shared.infrastructure.clock import SystemClock
from agilina_api.shared.infrastructure.database.session import (
    create_engine_for,
    create_session_factory,
)
from agilina_api.shared.infrastructure.mail.renderer import JinjaEmailRenderer
from agilina_api.shared.infrastructure.mail.smtp_mailer import SmtpMailer
from agilina_api.shared.infrastructure.settings import Settings
from agilina_api.teams.application.commands.change_member_role import ChangeMemberRoleHandler
from agilina_api.teams.application.commands.create_team import CreateTeamHandler
from agilina_api.teams.application.commands.create_team_as_admin import CreateTeamAsAdminHandler
from agilina_api.teams.application.commands.reconfigure_sprint import ReconfigureSprintHandler
from agilina_api.teams.application.commands.remove_member import RemoveMemberHandler
from agilina_api.teams.application.commands.start_sprint import StartSprintHandler
from agilina_api.teams.application.ports.outbound import TeamQueries
from agilina_api.teams.application.queries.get_active_sprint import GetActiveSprintHandler
from agilina_api.teams.application.queries.get_team import GetTeamHandler
from agilina_api.teams.application.queries.get_team_dashboard import GetTeamDashboardHandler
from agilina_api.teams.application.queries.get_team_user import GetTeamUserHandler
from agilina_api.teams.application.queries.list_my_teams import ListMyTeamsHandler
from agilina_api.teams.application.queries.list_team_members import ListTeamMembersHandler
from agilina_api.teams.infrastructure.persistence.sql_sprint_queries import SqlSprintQueries
from agilina_api.teams.infrastructure.persistence.team_queries import SqlTeamQueries
from agilina_api.teams.infrastructure.persistence.unit_of_work import teams_unit_of_work_factory


@dataclass
class Container:
    tenant: Tenant
    engine: AsyncEngine
    invitation_status: GetInvitationStatusHandler
    activate_account: ActivateAccountHandler
    request_new_invitation: RequestNewInvitationHandler
    issue_invitation: IssueInvitationHandler
    invite_to_team: InviteToTeamHandler
    create_team: CreateTeamHandler
    create_team_as_admin: CreateTeamAsAdminHandler
    list_my_teams: ListMyTeamsHandler
    get_team: GetTeamHandler
    list_team_members: ListTeamMembersHandler
    get_team_user: GetTeamUserHandler
    change_member_role: ChangeMemberRoleHandler
    remove_member: RemoveMemberHandler
    start_sprint: StartSprintHandler
    reconfigure_sprint: ReconfigureSprintHandler
    get_active_sprint: GetActiveSprintHandler
    get_team_dashboard: GetTeamDashboardHandler
    get_ceremony_context: GetCeremonyContextHandler
    team_queries: TeamQueries
    authenticated_users: AuthenticatedUsers
    authenticated_workers: AuthenticatedWorkers
    team_access: TeamAccess
    identity_provider: KeycloakIdentityProvider
    access_token_verifier: KeycloakAccessTokenVerifier

    async def aclose(self) -> None:
        await self.identity_provider.aclose()
        await self.access_token_verifier.aclose()
        await self.engine.dispose()


def build_container(settings: Settings, tenant: Tenant) -> Container:
    """Nothing here connects to anything: sessions, HTTP clients and SMTP are used lazily,
    so building it needs neither PostgreSQL nor Keycloak."""
    clock = SystemClock()
    engine = create_engine_for(
        settings.tenant_dsn(tenant.slug), echo=settings.log_level.upper() == "DEBUG"
    )
    session_factory = create_session_factory(engine)
    realm = settings.tenant_realm(tenant.slug)
    renderer = JinjaEmailRenderer()
    mailer = SmtpMailer(
        host=settings.smtp_host,
        port=settings.smtp_port,
        sender=settings.mail_from,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        security=settings.smtp_security,
    )
    identity_provider = KeycloakIdentityProvider(
        base_url=settings.keycloak_url,
        realm=realm,
        client_id=settings.keycloak_api_client,
        client_secret=settings.tenant_api_secret(tenant.slug).get_secret_value(),
    )
    realm_url = f"{settings.keycloak_public_url.rstrip('/')}/realms/{realm}"
    access_token_verifier = KeycloakAccessTokenVerifier(
        # The keys are read through the API's own route to Keycloak, but the issuer a token
        # carries is the public one.
        jwks_url=(
            f"{settings.keycloak_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/certs"
        ),
        issuer=realm_url,
        audience=settings.keycloak_api_client,
        clock=clock,
    )
    identity_uow = identity_unit_of_work_factory(session_factory, team_membership_factory(clock))
    teams_uow = teams_unit_of_work_factory(session_factory)
    team_queries = SqlTeamQueries(session_factory)
    sprint_queries = SqlSprintQueries(session_factory)
    get_active_sprint = GetActiveSprintHandler(sprint_queries, clock)
    user_contacts = SqlUserContacts(session_factory)
    team_contacts = TeamsBackedContacts(team_queries, user_contacts)
    # The web lives under the tenant's name (``/<tenant>/…``): its first segment decides
    # which realm signs the person in.
    tenant_web_url = f"{settings.web_public_url.rstrip('/')}/{tenant.slug}"
    issue_invitation = IssueInvitationHandler(
        identity_uow,
        SecretsActivationTokenGenerator(),
        renderer,
        mailer,
        clock,
        f"{tenant_web_url}/activate",
    )

    return Container(
        tenant=tenant,
        engine=engine,
        invitation_status=GetInvitationStatusHandler(SqlInvitationQueries(session_factory), clock),
        activate_account=ActivateAccountHandler(identity_uow, identity_provider, clock),
        request_new_invitation=RequestNewInvitationHandler(
            identity_uow, team_contacts, renderer, mailer, clock
        ),
        issue_invitation=issue_invitation,
        invite_to_team=InviteToTeamHandler(
            identity_uow,
            team_contacts,
            issue_invitation,
            renderer,
            mailer,
            clock,
            # The notice to an existing account links to the team, never to an activation.
            f"{tenant_web_url}/teams",
        ),
        create_team=CreateTeamHandler(teams_uow, clock),
        create_team_as_admin=CreateTeamAsAdminHandler(teams_uow, clock),
        list_my_teams=ListMyTeamsHandler(team_queries),
        get_team=GetTeamHandler(team_queries),
        list_team_members=ListTeamMembersHandler(
            team_queries, IdentityBackedMemberContacts(user_contacts)
        ),
        get_team_user=GetTeamUserHandler(team_queries, IdentityBackedMemberContacts(user_contacts)),
        change_member_role=ChangeMemberRoleHandler(teams_uow, clock),
        remove_member=RemoveMemberHandler(teams_uow, clock),
        start_sprint=StartSprintHandler(teams_uow),
        reconfigure_sprint=ReconfigureSprintHandler(teams_uow),
        get_active_sprint=get_active_sprint,
        get_team_dashboard=GetTeamDashboardHandler(team_queries, get_active_sprint),
        get_ceremony_context=GetCeremonyContextHandler(
            SqlCeremonyQueries(session_factory),
            TeamsBackedCeremonyRoster(team_queries, sprint_queries),
            IdentityBackedParticipantNames(user_contacts),
        ),
        team_queries=team_queries,
        authenticated_users=KeycloakAuthenticatedUsers(access_token_verifier, session_factory),
        # The same verifier: the worker's token is one of this tenant's realm, for this API.
        authenticated_workers=KeycloakAuthenticatedWorkers(
            access_token_verifier, settings.keycloak_worker_client
        ),
        # The teams query answers the shared port as it is: the membership is checked
        # against the stored role, never against a claim of the token.
        team_access=team_queries,
        identity_provider=identity_provider,
        access_token_verifier=access_token_verifier,
    )
