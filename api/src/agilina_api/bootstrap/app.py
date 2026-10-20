"""API entry point and composition root.

Run: ``make api`` · Interactive documentation: http://localhost:8000/docs
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agilina_api import __version__
from agilina_api.bootstrap.tenants import TenantContainers, from_container
from agilina_api.ceremonies.presentation.http import dailies_router
from agilina_api.ceremonies.presentation.http import dependencies as ceremonies_dependencies
from agilina_api.ceremonies.presentation.http import router as ceremonies_router
from agilina_api.ceremonies.presentation.http.errors import CEREMONIES_ERRORS
from agilina_api.identity.presentation.http import dependencies as identity_dependencies
from agilina_api.identity.presentation.http import router as identity_router
from agilina_api.identity.presentation.http.errors import IDENTITY_ERRORS
from agilina_api.shared.application.health import GetLiveness, GetReadiness
from agilina_api.shared.infrastructure.clock import SystemClock
from agilina_api.shared.infrastructure.database.session import (
    create_engine_for,
    create_session_factory,
)
from agilina_api.shared.infrastructure.database_probe import SqlDatabaseProbe
from agilina_api.shared.infrastructure.logging_setup import configure_logging, get_logger
from agilina_api.shared.infrastructure.scheduler import create_scheduler
from agilina_api.shared.infrastructure.settings import get_settings
from agilina_api.shared.infrastructure.tenancy.sql_tenant_directory import SqlTenantDirectory
from agilina_api.shared.presentation.http import health_router, tenancy_router
from agilina_api.shared.presentation.http.access import (
    get_authenticated_users,
    get_authenticated_workers,
    get_team_access,
)
from agilina_api.shared.presentation.http.dependencies import (
    get_liveness_query,
    get_readiness_query,
)
from agilina_api.shared.presentation.http.error_handlers import (
    SHARED_ERRORS,
    register_error_handlers,
)
from agilina_api.shared.presentation.http.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from agilina_api.shared.presentation.http.tenancy import get_tenant_directory
from agilina_api.teams.presentation.http import dependencies as teams_dependencies
from agilina_api.teams.presentation.http import router as teams_router
from agilina_api.teams.presentation.http import users_router
from agilina_api.teams.presentation.http.errors import TEAMS_ERRORS

logger = get_logger(__name__)

DESCRIPTION = """
Source of truth of the Agilina domain.

This specification is the contract with the web application and with the agent
worker: it is generated from the types, so it cannot drift from the code.

Every request that touches a tenant's data names it in the `X-Agilina-Tenant` header
(`400 tenant_required` without it, `404 tenant_not_found` for one that does not exist or is
suspended). Only `/health` and the documentation need no tenant.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start the scheduler with the application and stop it with it.

    If the database is unavailable, the API stays up without a scheduler and
    logs it: a deferred job must not bring the API down.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting agilina-api %s in environment %s", __version__, settings.environment)

    scheduler = None
    try:
        scheduler = create_scheduler(settings)
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Scheduler started")
    except Exception as error:  # running without a scheduler is degradation, not a crash
        app.state.scheduler = None
        logger.warning("The scheduler could not start: %s", error)

    yield

    await app.state.tenant_containers.aclose()
    await app.state.platform_engine.dispose()
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Agilina API",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Added last, so it is the outermost: every response, errors included, carries the id.
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router.router)
    app.include_router(tenancy_router.router)
    app.include_router(ceremonies_router.router)
    app.include_router(dailies_router.router)
    app.include_router(identity_router.router)
    app.include_router(teams_router.router)
    app.include_router(users_router.router)
    app.include_router(identity_router.team_invitations_router)
    register_error_handlers(
        app, (*SHARED_ERRORS, *IDENTITY_ERRORS, *TEAMS_ERRORS, *CEREMONIES_ERRORS)
    )

    # Wiring: presentation declares what it needs, this is where it is provided.
    # The platform's catalog: which tenants exist (and, further on, the scheduler's jobs).
    platform_engine = create_engine_for(settings.platform_dsn)
    platform_sessions = create_session_factory(platform_engine)
    tenants = SqlTenantDirectory(platform_sessions, SystemClock())
    app.state.platform_engine = platform_engine
    app.state.tenant_containers = TenantContainers(settings)

    liveness = GetLiveness(__version__, settings.environment)
    readiness = GetReadiness(SqlDatabaseProbe(platform_sessions), __version__, settings.environment)
    app.dependency_overrides[get_tenant_directory] = lambda: tenants
    # Everything that touches a tenant's data comes from the graph of the tenant the request
    # names (``X-Agilina-Tenant``): its own database, its own realm.
    overrides = {
        identity_dependencies.get_invitation_status_handler: from_container(
            lambda container: container.invitation_status
        ),
        identity_dependencies.get_activate_account_handler: from_container(
            lambda container: container.activate_account
        ),
        identity_dependencies.get_request_new_invitation_handler: from_container(
            lambda container: container.request_new_invitation
        ),
        identity_dependencies.get_invite_to_team_handler: from_container(
            lambda container: container.invite_to_team
        ),
        teams_dependencies.get_create_team_as_admin_handler: from_container(
            lambda container: container.create_team_as_admin
        ),
        teams_dependencies.get_list_my_teams_handler: from_container(
            lambda container: container.list_my_teams
        ),
        teams_dependencies.get_get_team_handler: from_container(
            lambda container: container.get_team
        ),
        teams_dependencies.get_list_team_members_handler: from_container(
            lambda container: container.list_team_members
        ),
        teams_dependencies.get_get_team_user_handler: from_container(
            lambda container: container.get_team_user
        ),
        teams_dependencies.get_change_member_role_handler: from_container(
            lambda container: container.change_member_role
        ),
        teams_dependencies.get_remove_member_handler: from_container(
            lambda container: container.remove_member
        ),
        teams_dependencies.get_start_sprint_handler: from_container(
            lambda container: container.start_sprint
        ),
        teams_dependencies.get_reconfigure_sprint_handler: from_container(
            lambda container: container.reconfigure_sprint
        ),
        teams_dependencies.get_get_active_sprint_handler: from_container(
            lambda container: container.get_active_sprint
        ),
        teams_dependencies.get_get_team_dashboard_handler: from_container(
            lambda container: container.get_team_dashboard
        ),
        ceremonies_dependencies.get_get_ceremony_context_handler: from_container(
            lambda container: container.get_ceremony_context
        ),
        ceremonies_dependencies.get_deliver_ceremony_result_handler: from_container(
            lambda container: container.deliver_ceremony_result
        ),
        ceremonies_dependencies.get_join_current_daily_handler: from_container(
            lambda container: container.join_current_daily
        ),
        get_authenticated_users: from_container(lambda container: container.authenticated_users),
        get_authenticated_workers: from_container(
            lambda container: container.authenticated_workers
        ),
        get_team_access: from_container(lambda container: container.team_access),
    }
    app.dependency_overrides.update(overrides)
    app.dependency_overrides[get_liveness_query] = lambda: liveness
    app.dependency_overrides[get_readiness_query] = lambda: readiness
    return app


app = create_app()
